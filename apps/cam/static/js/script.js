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