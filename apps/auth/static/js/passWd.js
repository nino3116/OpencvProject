document.addEventListener("DOMContentLoaded", function () {
    const passwordField = document.getElementById("floatingPassword");
    const passwordFeedback = document.createElement("small");
    passwordFeedback.style.color = "white";
    passwordField.parentNode.appendChild(passwordFeedback);

    passwordField.addEventListener("input", function () {
        const password = passwordField.value;
        const regex = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}/;

        if (password.length < 8) {
            passwordFeedback.textContent = "비밀번호는 최소 8자 이상이어야 합니다.";
        } else if (!regex.test(password)) {
            passwordFeedback.textContent = "비밀번호는 문자, 숫자, 특수문자를 포함해야 합니다.";
        } else {
            passwordFeedback.textContent = ""; // 비밀번호가 조건을 만족하면 피드백을 지움
        }
    });
});