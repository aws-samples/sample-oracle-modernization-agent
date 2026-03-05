// 전역 변수
const API_BASE = '/amzn-bo/api';
let orderTrendChart, userGradeChart;

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
});

// 앱 초기화
function initializeApp() {
    // 실제 데이터 범위로 날짜 설정
    document.getElementById('startDate').value = '2024-08-01';
    document.getElementById('endDate').value = '2025-08-31';
    
    loadDashboardData();
    loadUsersTab();
    updateLastUpdateTime();
    
    // 5분마다 자동 새로고침
    setInterval(() => {
        loadDashboardData();
        updateLastUpdateTime();
    }, 300000);
}

// 이벤트 리스너 설정
function setupEventListeners() {
    // 탭 변경 이벤트
    document.querySelectorAll('#mainTabs a[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(e) {
            const target = e.target.getAttribute('href');
            if (target === '#users') loadUsersTab();
            else if (target === '#products') loadProductsTab();
            else if (target === '#orders') loadOrdersTab();
        });
    });
}

// 대시보드 데이터 로드
async function loadDashboardData() {
    try {
        // 통계 데이터 로드
        await Promise.all([
            loadUserStats(),
            loadProductStats(),
            loadOrderStats(),
            loadCharts()
        ]);
    } catch (error) {
        console.error('대시보드 데이터 로드 실패:', error);
        showError('대시보드 데이터를 불러오는데 실패했습니다.');
    }
}

// 사용자 통계 로드
async function loadUserStats() {
    try {
        console.log('Loading user stats...');
        const response = await fetch(`${API_BASE}/users?page=1&size=1`);
        const result = await response.json();
        console.log('User stats response:', result);
        
        const data = result.data || result;
        const totalUsers = data.totalElements || 0;
        
        console.log('Total users:', totalUsers);
        document.getElementById('totalUsers').textContent = totalUsers;
        document.getElementById('todayUsers').textContent = `최근 +0`; // 실제 데이터에 최근 가입이 없음
    } catch (error) {
        console.error('사용자 통계 로드 실패:', error);
        document.getElementById('totalUsers').textContent = '0';
    }
}

// 상품 통계 로드
async function loadProductStats() {
    try {
        console.log('Loading product stats...');
        const response = await fetch(`${API_BASE}/products?page=1&size=1`);
        const result = await response.json();
        console.log('Product stats response:', result);
        
        const data = result.data || result;
        const totalProducts = data.totalElements || 0;
        
        console.log('Total products:', totalProducts);
        document.getElementById('totalProducts').textContent = totalProducts;
        document.getElementById('todayProducts').textContent = `최근 +0`; // 실제 데이터에 최근 등록이 없음
    } catch (error) {
        console.error('상품 통계 로드 실패:', error);
        document.getElementById('totalProducts').textContent = '0';
    }
}

// 주문 통계 로드
async function loadOrderStats() {
    try {
        console.log('Loading order stats from API...');
        
        // 주문 상태별 통계에서 실제 매출 데이터 가져오기
        const statusResponse = await fetch(`${API_BASE}/orders/statistics/status`);
        const statusResult = await statusResponse.json();
        
        if (statusResult.success && statusResult.data) {
            // 취소/환불 제외한 실제 매출 계산
            const validStatuses = statusResult.data.filter(item => 
                !['CANCELLED', 'REFUNDED'].includes(item.ORDER_STATUS)
            );
            
            const totalOrders = validStatuses.reduce((sum, item) => sum + item.ORDER_COUNT, 0);
            const totalRevenue = validStatuses.reduce((sum, item) => sum + item.TOTAL_AMOUNT, 0);
            
            document.getElementById('totalOrders').textContent = totalOrders;
            document.getElementById('totalRevenue').textContent = formatCurrency(totalRevenue);
            
            // 최근 데이터는 실제로 없으므로 0으로 표시
            document.getElementById('todayOrders').textContent = `최근 +0`;
            document.getElementById('todayRevenue').textContent = `최근 +₩0`;
            
            console.log('실제 API 통계:', { totalOrders, totalRevenue });
        }
        
    } catch (error) {
        console.error('주문 통계 로드 실패:', error);
        document.getElementById('totalOrders').textContent = '0';
        document.getElementById('totalRevenue').textContent = '₩0';
    }
}

// 주문 통계 로드
async function loadOrderStats() {
    try {
        const response = await fetch(`${API_BASE}/orders?page=1&size=1`);
        const data = await response.json();
        
        document.getElementById('totalOrders').textContent = data.totalElements || 0;
        document.getElementById('todayOrders').textContent = `오늘 +${Math.floor(Math.random() * 20)}`;
        
        // 매출 계산 (임시)
        const revenue = (data.totalElements || 0) * 50000;
        document.getElementById('totalRevenue').textContent = formatCurrency(revenue);
        document.getElementById('todayRevenue').textContent = `오늘 +${formatCurrency(Math.floor(Math.random() * 1000000))}`;
    } catch (error) {
        console.error('주문 통계 로드 실패:', error);
    }
}

// 차트 로드
async function loadCharts() {
    loadOrderTrendChart();
    loadUserGradeChart();
}

// 주문 트렌드 차트
function loadOrderTrendChart() {
    const ctx = document.getElementById('orderTrendChart').getContext('2d');
    
    if (orderTrendChart) {
        orderTrendChart.destroy();
    }
    
    const labels = [];
    const data = [];
    
    for (let i = 6; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        labels.push(date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }));
        data.push(Math.floor(Math.random() * 100) + 50);
    }
    
    orderTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '주문 수',
                data: data,
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// 사용자 등급 차트
async function loadUserGradeChart() {
    const ctx = document.getElementById('userGradeChart').getContext('2d');
    
    if (userGradeChart) {
        userGradeChart.destroy();
    }
    
    try {
        // 실제 사용자 등급 통계 API 호출
        const response = await fetch(`${API_BASE}/users/grade-statistics`);
        const result = await response.json();
        
        if (result.success && result.data) {
            const labels = result.data.map(item => item.USER_GRADE);
            const data = result.data.map(item => item.USER_PERCENTAGE);
            const colors = ['#dc3545', '#ffc107', '#198754', '#6c757d']; // VIP, PREMIUM, REGULAR, NEW
            
            userGradeChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: colors.slice(0, labels.length)
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        }
    } catch (error) {
        console.error('사용자 등급 차트 로드 실패:', error);
        // 실패 시 기본 차트 표시
        userGradeChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['데이터 없음'],
                datasets: [{
                    data: [100],
                    backgroundColor: ['#6c757d']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
}

// 유틸리티 함수들
function formatCurrency(amount) {
    return new Intl.NumberFormat('ko-KR', {
        style: 'currency',
        currency: 'KRW',
        minimumFractionDigits: 0
    }).format(amount);
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('ko-KR');
}

function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString('ko-KR');
}

function showError(message) {
    alert('오류: ' + message);
}

function showSuccess(message) {
    alert('성공: ' + message);
}

function refreshData() {
    loadDashboardData();
    
    // 현재 활성 탭 새로고침
    const activeTab = document.querySelector('#mainTabs .nav-link.active');
    const target = activeTab.getAttribute('href');
    
    if (target === '#users') loadUsersTab();
    else if (target === '#products') loadProductsTab();
    else if (target === '#orders') loadOrdersTab();
    
    updateLastUpdateTime();
    showSuccess('데이터가 새로고침되었습니다.');
}

function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = 
        `마지막 업데이트: ${now.toLocaleTimeString('ko-KR')}`;
}

// 모달 표시
function showModal(title, content) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = content;
    
    const modal = new bootstrap.Modal(document.getElementById('detailModal'));
    modal.show();
}

// 로딩 표시
function showLoading(containerId) {
    document.getElementById(containerId).innerHTML = `
        <div class="loading">
            <i class="fas fa-spinner fa-spin fa-2x"></i>
            <p class="mt-2">데이터를 불러오는 중...</p>
        </div>
    `;
}
