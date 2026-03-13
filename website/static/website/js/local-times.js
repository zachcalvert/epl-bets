(function () {
  var SHORT_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var LONG_DAYS = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
  ];
  var SHORT_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  var LONG_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  function pad(n) {
    return n < 10 ? "0" + n : "" + n;
  }

  function formatLocal(date, fmt) {
    var day = SHORT_DAYS[date.getDay()];
    var dd = date.getDate();
    var mon = SHORT_MONTHS[date.getMonth()];
    var hh = pad(date.getHours());
    var mm = pad(date.getMinutes());

    if (fmt === "long") {
      var longDay = LONG_DAYS[date.getDay()];
      var longMon = LONG_MONTHS[date.getMonth()];
      return longDay + ", " + dd + " " + longMon + " " + date.getFullYear() + " \u2014 " + hh + ":" + mm;
    }
    if (fmt === "badge") {
      return day + " " + hh + ":" + mm;
    }
    // short (default)
    return day + " " + dd + " " + mon + ", " + hh + ":" + mm;
  }

  function convertTimes(root) {
    var els = (root || document).querySelectorAll("time[datetime]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var iso = el.getAttribute("datetime");
      if (!iso) continue;
      var date = new Date(iso);
      if (isNaN(date.getTime())) continue;
      var fmt = el.getAttribute("data-format") || "short";
      el.textContent = formatLocal(date, fmt);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    convertTimes();
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    convertTimes(e.detail.target);
  });
})();
