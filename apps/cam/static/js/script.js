const content = document.getElementById('content');
const additionalContent = document.getElementById('additionalContent');
const topButton = document.getElementById('topButton');

let page = 1; // 페이지 번호
const itemsPerPage = 10; // 페이지당 아이템 수

// 스크롤 이벤트 핸들러
content.addEventListener('scroll', () => {

    // 스크롤 위치에 따라 top button 표시/숨김
    if (content.scrollTop > 200) {
        topButton.style.display = 'block';
    } else {
        topButton.style.display = 'none';
    }
});

// top button 클릭 이벤트 핸들러
topButton.addEventListener('click', () => {
    content.scrollTo({ top: 0, behavior: 'smooth' });
});

// 초기 콘텐츠 로드
// additionalContent.innerHTML = generateContent(page, itemsPerPage);
