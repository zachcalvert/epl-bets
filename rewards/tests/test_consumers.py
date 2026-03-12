from unittest.mock import Mock

import pytest

from rewards.consumers import NotificationConsumer
from rewards.tests.factories import RewardDistributionFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def build_consumer(user=None):
    consumer = NotificationConsumer()
    consumer.scope = {"user": user}
    consumer.channel_name = "test-channel"
    return consumer


class TestNotificationConsumerConnect:
    def test_connect_joins_user_group(self, monkeypatch):
        user = UserFactory()
        consumer = build_consumer(user)
        accept = Mock()
        join_group = Mock()
        monkeypatch.setattr(consumer, "accept", accept)
        monkeypatch.setattr(consumer, "_join_group", join_group)

        consumer.connect()

        accept.assert_called_once_with()
        join_group.assert_called_once_with(f"user_notifications_{user.pk}")

    def test_connect_rejects_anonymous(self, monkeypatch):
        consumer = build_consumer(user=None)
        close = Mock()
        monkeypatch.setattr(consumer, "close", close)

        consumer.connect()

        close.assert_called_once_with()
        assert consumer.group_name is None

    def test_connect_rejects_unauthenticated_user(self, monkeypatch):
        anon = Mock(is_authenticated=False)
        consumer = build_consumer(user=anon)
        close = Mock()
        monkeypatch.setattr(consumer, "close", close)

        consumer.connect()

        close.assert_called_once_with()


class TestNotificationConsumerDisconnect:
    def test_disconnect_leaves_group(self, monkeypatch):
        user = UserFactory()
        consumer = build_consumer(user)
        consumer.group_name = f"user_notifications_{user.pk}"
        layer = SimpleLayer()
        monkeypatch.setattr("channels.layers.get_channel_layer", lambda: layer)

        consumer.disconnect(1000)

        assert layer.discarded == [(f"user_notifications_{user.pk}", "test-channel")]
        assert consumer.group_name is None

    def test_disconnect_noops_when_no_group(self, monkeypatch):
        consumer = build_consumer(user=None)
        layer = SimpleLayer()
        monkeypatch.setattr("channels.layers.get_channel_layer", lambda: layer)

        consumer.disconnect(1000)

        assert layer.discarded == []


class TestNotificationConsumerEvents:
    def test_reward_notification_renders_and_sends(self, monkeypatch):
        dist = RewardDistributionFactory()
        consumer = build_consumer(dist.user)
        consumer.send = Mock()
        monkeypatch.setattr(
            "rewards.consumers.render_to_string",
            lambda template, context: f"{template}:{context['distribution'].pk}",
        )

        consumer.reward_notification({"distribution_id": dist.pk})

        consumer.send.assert_called_once()
        text = consumer.send.call_args.kwargs["text_data"]
        assert "rewards/partials/reward_toast_oob.html" in text
        assert str(dist.pk) in text

    def test_reward_notification_handles_missing_distribution(self):
        consumer = build_consumer(user=None)
        consumer.send = Mock()

        consumer.reward_notification({"distribution_id": 999999})

        consumer.send.assert_not_called()

    def test_reward_notification_swallows_render_errors(self, monkeypatch):
        dist = RewardDistributionFactory()
        consumer = build_consumer(dist.user)
        consumer.send = Mock(side_effect=RuntimeError("send failed"))
        monkeypatch.setattr(
            "rewards.consumers.render_to_string",
            lambda template, context: "payload",
        )

        consumer.reward_notification({"distribution_id": dist.pk})

        consumer.send.assert_called_once_with(text_data="payload")


class TestBroadcastOnDistribute:
    @pytest.mark.django_db(transaction=True)
    def test_distribute_broadcasts_to_each_user(self, monkeypatch):
        from rewards.models import Reward

        users = UserFactory.create_batch(3)
        reward = Reward.objects.create(name="Test", amount=10)

        sent_events = []

        def fake_group_send(group, event):
            sent_events.append((group, event))

        layer = Mock()
        layer.group_send = Mock(side_effect=lambda g, e: fake_group_send(g, e))
        monkeypatch.setattr("channels.layers.get_channel_layer", lambda: layer)

        distributions = reward.distribute_to_users(users)

        assert len(distributions) == 3
        assert len(sent_events) == 3
        for dist in distributions:
            group = f"user_notifications_{dist.user_id}"
            matching = [e for e in sent_events if e[0] == group]
            assert len(matching) == 1
            assert matching[0][1]["type"] == "reward_notification"
            assert matching[0][1]["distribution_id"] == dist.pk

    @pytest.mark.django_db(transaction=True)
    def test_distribute_does_not_broadcast_when_no_new_distributions(self, monkeypatch):
        from rewards.models import Reward

        user = UserFactory()
        reward = Reward.objects.create(name="Test", amount=10)
        reward.distribute_to_users([user])  # first distribution

        sent_events = []
        layer = Mock()
        layer.group_send = Mock(side_effect=lambda g, e: sent_events.append((g, e)))
        monkeypatch.setattr("channels.layers.get_channel_layer", lambda: layer)

        distributions = reward.distribute_to_users([user])  # duplicate

        assert len(distributions) == 0
        assert len(sent_events) == 0


class SimpleLayer:
    def __init__(self):
        self.added = []
        self.discarded = []

    async def group_add(self, group, channel):
        self.added.append((group, channel))

    async def group_discard(self, group, channel):
        self.discarded.append((group, channel))
