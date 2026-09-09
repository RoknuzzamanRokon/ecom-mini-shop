document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-quantity-selector]").forEach(function (selector) {
    var input = selector.querySelector("[data-quantity-input]");
    var decreaseBtn = selector.querySelector("[data-quantity-decrease]");
    var increaseBtn = selector.querySelector("[data-quantity-increase]");
    if (!input) return;

    var min = parseInt(input.min || "1", 10);
    var max = input.max ? parseInt(input.max, 10) : null;

    function clamp(value) {
      if (isNaN(value) || value < min) value = min;
      if (max && value > max) value = max;
      return value;
    }

    if (decreaseBtn) {
      decreaseBtn.addEventListener("click", function () {
        input.value = clamp(parseInt(input.value, 10) - 1);
      });
    }
    if (increaseBtn) {
      increaseBtn.addEventListener("click", function () {
        input.value = clamp(parseInt(input.value, 10) + 1);
      });
    }
    input.addEventListener("change", function () {
      input.value = clamp(parseInt(input.value, 10));
    });
  });
});
