// const content = document.getElementById('content');
// const additionalContent = document.getElementById('additionalContent');
// const topButton = document.getElementById('topButton');

// let page = 1; // 페이지 번호
// const itemsPerPage = 10; // 페이지당 아이템 수

// // 스크롤 이벤트 핸들러
// content.addEventListener('scroll', () => {

//     // 스크롤 위치에 따라 top button 표시/숨김
//     if (content.scrollTop > 200) {
//         topButton.style.display = 'block';
//     } else {
//         topButton.style.display = 'none';
//     }
// });

// // top button 클릭 이벤트 핸들러
// topButton.addEventListener('click', () => {
//     content.scrollTo({ top: 0, behavior: 'smooth' });
// });

// 초기 콘텐츠 로드
// additionalContent.innerHTML = generateContent(page, itemsPerPage);

$(document).ready(function () {
    let topButton = $("#topButton"); // 버튼 가져오기

    // 스크롤하면 버튼이 나타나고 사라짐
    $(window).scroll(function () {
        if ($(window).scrollTop() > 350) { 
            topButton.fadeIn(); // 200px 이상 스크롤하면 버튼 보이기
        } else {
            topButton.fadeOut(); // 위로 올라가면 버튼 숨기기
        }
    });
    // 버튼 클릭하면 최상단으로 부드럽게 이동
    topButton.click(function () {
        $("html, body").animate({ scrollTop: 0 }, "slow");
    });
});


document.addEventListener("DOMContentLoaded", function () {
    // 모든 날짜별 전체 선택 체크박스 가져오기
    const allSelectAllCheckboxes = document.querySelectorAll(".selectAllCheckbox");

    allSelectAllCheckboxes.forEach((selectAllCheckbox) => {
      const date = selectAllCheckbox.dataset.date; // 해당 날짜 가져오기
      const videoCheckboxes = document.querySelectorAll(`.videoCheckbox-${date}`);

      // 날짜별 전체 선택 체크박스 클릭 이벤트
      selectAllCheckbox.addEventListener("change", function () {
        videoCheckboxes.forEach((checkbox) => {
          checkbox.checked = selectAllCheckbox.checked;
        });
      });

      // 개별 체크박스 클릭 이벤트
      videoCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", function () {
          const allChecked = Array.from(videoCheckboxes).every((cb) => cb.checked);
          selectAllCheckbox.checked = allChecked;
        });
      });
    });
  });