document.addEventListener("DOMContentLoaded", function () {
  var canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  document.querySelectorAll("[data-gallery]").forEach(function (gallery) {
    var frame = gallery.querySelector("[data-gallery-frame]");
    var mainImage = gallery.querySelector("[data-gallery-main]");
    var thumbs = gallery.querySelectorAll("[data-gallery-thumb]");
    if (!mainImage) return;

    thumbs.forEach(function (thumb) {
      thumb.addEventListener("click", function () {
        var url = thumb.getAttribute("data-image-url");
        if (!url) return;
        mainImage.setAttribute("src", url);
        thumbs.forEach(function (t) {
          t.classList.remove("border-primary");
          t.classList.add("border-transparent");
        });
        thumb.classList.remove("border-transparent");
        thumb.classList.add("border-primary");
      });
    });

    if (canHover && frame) {
      mainImage.style.transition = "transform 0.15s ease-out";

      frame.addEventListener("mousemove", function (event) {
        var rect = frame.getBoundingClientRect();
        var x = ((event.clientX - rect.left) / rect.width) * 100;
        var y = ((event.clientY - rect.top) / rect.height) * 100;
        mainImage.style.transformOrigin = x + "% " + y + "%";
        mainImage.style.transform = "scale(2.2)";
      });

      frame.addEventListener("mouseleave", function () {
        mainImage.style.transform = "scale(1)";
        mainImage.style.transformOrigin = "center";
      });
    }
  });
});
