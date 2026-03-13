(function () {
  "use strict";

  var SELECTION_TO_ATTR = {
    HOME_WIN: "oddsHome",
    DRAW: "oddsDraw",
    AWAY_WIN: "oddsAway",
  };

  function updatePayoutPreview(form) {
    var display = form.querySelector("[data-payout-display]");
    if (!display) return;

    var selectionInput =
      form.querySelector('input[name="selection"]:checked') ||
      form.querySelector('input[name="selection"][type="hidden"]');
    var stakeInput = form.querySelector('input[name="stake"]');

    if (!selectionInput || !stakeInput) {
      display.classList.add("hidden");
      return;
    }

    var selection = selectionInput.value;
    var stake = parseFloat(stakeInput.value);
    var attrName = SELECTION_TO_ATTR[selection];

    if (!attrName || isNaN(stake) || stake <= 0) {
      display.classList.add("hidden");
      return;
    }

    var odds = parseFloat(form.dataset[attrName]);
    if (isNaN(odds) || odds <= 0) {
      display.classList.add("hidden");
      return;
    }

    var payout = (stake * odds).toFixed(2);
    form.querySelector("[data-payout-value]").textContent = payout;
    display.classList.remove("hidden");
  }

  document.body.addEventListener("input", function (e) {
    if (e.target.name === "stake") {
      var form = e.target.closest("form");
      if (form) updatePayoutPreview(form);
    }
  });

  document.body.addEventListener("change", function (e) {
    if (e.target.name === "selection") {
      var form = e.target.closest("form");
      if (form) updatePayoutPreview(form);
    }
  });
})();
