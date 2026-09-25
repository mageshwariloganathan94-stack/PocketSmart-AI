// PocketSmart AI Client-Side Scripts

document.addEventListener("DOMContentLoaded", () => {
    // 1. Quantity Stepper Controls (Home Planner)
    const counterButtons = document.querySelectorAll(".counter-btn");
    counterButtons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const action = btn.getAttribute("data-action");
            const targetId = btn.getAttribute("data-target");
            const input = document.getElementById(targetId);
            if (!input) return;

            let val = parseInt(input.value, 10) || 0;
            if (action === "inc") {
                val += 1;
            } else if (action === "dec") {
                val = Math.max(0, val - 1);
            }
            input.value = val;
        });
    });

    // 2. Jewelry Outfit Image Upload Preview
    const outfitInput = document.getElementById("outfit_image");
    const previewWrapper = document.getElementById("image_preview_wrapper");
    const previewImg = document.getElementById("outfit_preview_img");

    if (outfitInput && previewWrapper && previewImg) {
        outfitInput.addEventListener("change", function () {
            const file = this.files[0];
            if (file) {
                // Check size (under 10MB)
                if (file.size > 10 * 1024 * 1024) {
                    alert("Please select an image smaller than 10MB.");
                    this.value = "";
                    previewWrapper.style.display = "none";
                    return;
                }
                const reader = new FileReader();
                reader.onload = function (e) {
                    previewImg.src = e.target.result;
                    previewWrapper.style.display = "block";
                };
                reader.readAsDataURL(file);
            } else {
                previewWrapper.style.display = "none";
            }
        });
    }

    // 3. Form Submit Spinner Overlay
    const plannerForms = document.querySelectorAll(".planner-form");
    const loadingOverlay = document.getElementById("loading_overlay");
    const loadingMessage = document.getElementById("loading_message");

    plannerForms.forEach(form => {
        form.addEventListener("submit", () => {
            if (loadingOverlay) {
                loadingOverlay.style.display = "flex";
                if (loadingMessage) {
                    const plannerType = form.getAttribute("data-planner") || "Plan";
                    loadingMessage.innerText = `Analyzing budget & querying Gemini AI for your ${plannerType}...`;
                }
            }
        });
    });

    // 4. Alert Auto-Dismissal
    const alerts = document.querySelectorAll(".alert");
    alerts.forEach(alertBox => {
        setTimeout(() => {
            alertBox.style.opacity = "0";
            alertBox.style.transition = "opacity 0.5s ease";
            setTimeout(() => alertBox.remove(), 500);
        }, 5000);
    });

    // 5. Testimonial Rating Stars Clicker
    const starSelectors = document.querySelectorAll(".star-rating-select span");
    const ratingInput = document.getElementById("rating_value");
    if (starSelectors.length > 0 && ratingInput) {
        starSelectors.forEach((star, index) => {
            star.addEventListener("click", () => {
                const score = index + 1;
                ratingInput.value = score;
                starSelectors.forEach((s, i) => {
                    s.style.color = (i < score) ? "#f59e0b" : "#cbd5e1";
                });
            });
        });
    }
});

// Helper for currency formatting
function formatINR(number) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0
    }).format(number);
}
