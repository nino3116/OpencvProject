// // TOP 버튼 스크립트 코드
// $(document).ready(function () {
//   let topButton = $("#topButton"); // 버튼 가져오기

//   // 스크롤하면 버튼이 나타나고 사라짐
//   $(window).scroll(function () {
//     if ($(window).scrollTop() > 350) {
//       topButton.fadeIn(); // 350px 이상 스크롤하면 버튼 보이기
//     } else {
//       topButton.fadeOut(); // 위로 올라가면 버튼 숨기기
//     }
//   });
//   // 버튼 클릭하면 최상단으로 부드럽게 이동
//   topButton.click(function () {
//     $("html, body").animate({ scrollTop: 0 }, "slow");
//   });
// });


// 전체 선택 다중 선택 삭제 기능 스크립트
document.addEventListener("DOMContentLoaded", function () {
  // 모든 날짜별 전체 선택 체크박스 가져오기
  const allSelectAllCheckboxes = document.querySelectorAll(
    ".select-all-checkbox"
  );

  allSelectAllCheckboxes.forEach((selectAllCheckbox) => {
    const date = selectAllCheckbox.dataset.date; // 해당 날짜 가져오기
    const videoCheckboxes = document.querySelectorAll(`.video-checkbox${date}`);

    // 날짜별 전체 선택 체크박스 클릭 이벤트
    selectAllCheckbox.addEventListener("change", function () {
      videoCheckboxes.forEach((checkbox) => {
        checkbox.checked = selectAllCheckbox.checked;
      });
    });

    // 개별 체크박스 클릭 이벤트
    videoCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", function () {
        const allChecked = Array.from(videoCheckboxes).every(
          (cb) => cb.checked
        );
        selectAllCheckbox.checked = allChecked;
      });
    });
  });
});

// 부트스트랩 관련 툴팁 초기화를 위한 코드
const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))