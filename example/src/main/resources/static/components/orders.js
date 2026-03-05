// 주문 관리 관련 함수들
let currentOrdersPage = 1;
let ordersPageSize = 10;
let ordersFilters = {};

// 주문 탭 로드
async function loadOrdersTab() {
    showLoading('ordersContent');
    
    const content = `
        <!-- 검색 및 필터 -->
        <div class="search-filters">
            <div class="row g-3">
                <div class="col-md-2">
                    <input type="text" class="form-control" id="orderSearchKeyword" placeholder="주문ID 또는 고객명">
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="orderStatusFilter">
                        <option value="">전체 상태</option>
                        <option value="PENDING">주문확인</option>
                        <option value="CONFIRMED">주문승인</option>
                        <option value="PROCESSING">처리중</option>
                        <option value="SHIPPED">배송중</option>
                        <option value="DELIVERED">배송완료</option>
                        <option value="CANCELLED">취소</option>
                        <option value="RETURNED">반품</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="paymentMethodFilter">
                        <option value="">전체 결제방법</option>
                        <option value="CREDIT_CARD">신용카드</option>
                        <option value="BANK_TRANSFER">계좌이체</option>
                        <option value="VIRTUAL_ACCOUNT">가상계좌</option>
                        <option value="MOBILE_PAYMENT">모바일결제</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="orderSortBy">
                        <option value="createdAt">주문일순</option>
                        <option value="totalAmount">주문금액순</option>
                        <option value="customerName">고객명순</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="orderSortDirection">
                        <option value="DESC">내림차순</option>
                        <option value="ASC">오름차순</option>
                    </select>
                </div>
                <div class="col-md-1">
                    <button class="btn btn-primary w-100" onclick="searchOrders()">
                        <i class="fas fa-search"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- 주문 테이블 -->
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0"><i class="fas fa-shopping-cart"></i> 주문 목록</h5>
                <div>
                    <select class="form-select form-select-sm d-inline-block w-auto" id="ordersPageSize" onchange="changeOrdersPageSize()">
                        <option value="10">10개씩</option>
                        <option value="20">20개씩</option>
                        <option value="50">50개씩</option>
                    </select>
                </div>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead>
                            <tr>
                                <th>주문ID</th>
                                <th>고객명</th>
                                <th>상품수</th>
                                <th>총금액</th>
                                <th>결제방법</th>
                                <th>주문상태</th>
                                <th>주문일</th>
                                <th>배송예정일</th>
                            </tr>
                        </thead>
                        <tbody id="ordersTableBody">
                            <!-- 동적 컨텐츠 -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- 페이징 -->
        <nav class="mt-3">
            <ul class="pagination" id="ordersPagination">
                <!-- 동적 컨텐츠 -->
            </ul>
        </nav>
    `;
    
    document.getElementById('ordersContent').innerHTML = content;
    
    // 이벤트 리스너 추가
    document.getElementById('orderSearchKeyword').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') searchOrders();
    });
    
    await loadOrdersData();
}

// 주문 데이터 로드
async function loadOrdersData() {
    try {
        console.log('Loading orders data with filters:', ordersFilters);
        
        const params = new URLSearchParams({
            page: currentOrdersPage,
            size: ordersPageSize,
            ...ordersFilters
        });
        
        const url = `${API_BASE}/orders?${params}`;
        console.log('Fetching orders URL:', url);
        
        const response = await fetch(url);
        const result = await response.json();
        console.log('Orders API response:', result);
        
        // API 응답 구조 처리
        const data = result.data || result;
        console.log('Orders data:', data);
        
        renderOrdersTable(data.content || []);
        renderOrdersPagination(data);
        
    } catch (error) {
        console.error('주문 데이터 로드 실패:', error);
        document.getElementById('ordersTableBody').innerHTML = `
            <tr><td colspan="8" class="text-center text-danger">데이터를 불러오는데 실패했습니다: ${error.message}</td></tr>
        `;
    }
}

// 주문 테이블 렌더링
function renderOrdersTable(orders) {
    const tbody = document.getElementById('ordersTableBody');
    
    if (!orders || orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">데이터가 없습니다.</td></tr>';
        return;
    }
    
    tbody.innerHTML = orders.map(order => {
        // API 응답 필드명 매핑
        const customerName = order.customerName || order.userName || 'Unknown';
        const itemCount = order.itemCount || order.orderItemCount || 1;
        const paymentMethod = order.paymentMethod || 'UNKNOWN';
        const orderStatus = order.orderStatus || order.status || 'PENDING';
        
        return `
            <tr onclick="showOrderDetail('${order.orderId}')">
                <td><code>${order.orderId}</code></td>
                <td>${customerName}</td>
                <td>${itemCount}개</td>
                <td><strong>${formatCurrency(order.totalAmount)}</strong></td>
                <td><span class="badge bg-info">${getPaymentMethodText(paymentMethod)}</span></td>
                <td><span class="badge bg-${getOrderStatusBadgeColor(orderStatus)}">${getOrderStatusText(orderStatus)}</span></td>
                <td>${formatDate(order.createdAt || order.orderedAt)}</td>
                <td>${order.expectedDeliveryDate ? formatDate(order.expectedDeliveryDate) : '-'}</td>
            </tr>
        `;
    }).join('');
}

// 주문 페이징 렌더링
function renderOrdersPagination(data) {
    const pagination = document.getElementById('ordersPagination');
    const totalPages = data.totalPages || 1;
    const currentPage = data.page || currentOrdersPage;
    
    let html = '';
    
    // 이전 버튼
    html += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="goToOrdersPage(${currentPage - 1}); return false;">이전</a>
    </li>`;
    
    // 페이지 번호들
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<li class="page-item ${i === currentPage ? 'active' : ''}">
            <a class="page-link" href="#" onclick="goToOrdersPage(${i}); return false;">${i}</a>
        </li>`;
    }
    
    // 다음 버튼
    html += `<li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="goToOrdersPage(${currentPage + 1}); return false;">다음</a>
    </li>`;
    
    pagination.innerHTML = html;
}

// 주문 검색
function searchOrders() {
    const keyword = document.getElementById('orderSearchKeyword').value.toLowerCase();
    const status = document.getElementById('orderStatusFilter').value;
    const paymentMethod = document.getElementById('paymentMethodFilter').value;
    
    console.log('Searching orders:', { keyword, status, paymentMethod });
    
    // 테이블의 모든 행을 가져와서 필터링
    const tbody = document.getElementById('ordersTableBody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 8) return; // 헤더나 빈 행 제외
        
        const orderId = cells[0].textContent.toLowerCase();
        const customerName = cells[1].textContent.toLowerCase();
        const orderPaymentMethod = cells[4].textContent.trim(); // 결제방법 (5번째 컬럼)
        const orderStatus = cells[5].textContent.trim(); // 상태 (6번째 컬럼)
        
        let show = true;
        
        // 키워드 검색 (주문ID, 고객명에서)
        if (keyword && !orderId.includes(keyword) && !customerName.includes(keyword)) {
            show = false;
        }
        
        // 상태 필터
        if (status && !orderStatus.includes(status)) {
            show = false;
        }
        
        // 결제방법 필터
        if (paymentMethod && !orderPaymentMethod.includes(paymentMethod)) {
            show = false;
        }
        
        row.style.display = show ? '' : 'none';
    });
}

// 주문 페이지 이동
function goToOrdersPage(page) {
    console.log('Going to orders page:', page);
    currentOrdersPage = page;
    loadOrdersData();
}

// 주문 페이지 크기 변경
function changeOrdersPageSize() {
    ordersPageSize = parseInt(document.getElementById('ordersPageSize').value);
    currentOrdersPage = 1;
    loadOrdersData();
}

// 주문 상세 정보 표시
async function showOrderDetail(orderId) {
    try {
        const response = await fetch(`${API_BASE}/orders/${orderId}`);
        const result = await response.json();
        const order = result.data || result;
        
        // 실제 API 응답 필드명 사용
        const customerName = order.userName || order.customerName || 'Unknown';
        const customerEmail = order.userEmail || order.customerEmail || '-';
        const paymentMethod = order.paymentMethod || 'UNKNOWN';
        const orderStatus = order.orderStatus || order.status || 'PENDING';
        const orderNumber = order.orderNumber || order.orderId;
        
        const content = `
            <div class="row">
                <div class="col-md-6">
                    <h6>주문 정보</h6>
                    <table class="table table-sm">
                        <tr><th>주문 ID:</th><td><code>${order.orderId}</code></td></tr>
                        <tr><th>주문 번호:</th><td><code>${orderNumber}</code></td></tr>
                        <tr><th>고객명:</th><td>${customerName}</td></tr>
                        <tr><th>고객 이메일:</th><td>${customerEmail}</td></tr>
                        <tr><th>총 금액:</th><td><strong>${formatCurrency(order.totalAmount)}</strong></td></tr>
                        <tr><th>통화:</th><td>${order.currency || 'KRW'}</td></tr>
                        <tr><th>결제 방법:</th><td><span class="badge bg-info">${getPaymentMethodText(paymentMethod)}</span></td></tr>
                        <tr><th>주문 상태:</th><td><span class="badge bg-${getOrderStatusBadgeColor(orderStatus)}">${getOrderStatusText(orderStatus)}</span></td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6>배송 및 날짜 정보</h6>
                    <table class="table table-sm">
                        <tr><th>배송 주소:</th><td>${order.shippingAddress || '-'}</td></tr>
                        <tr><th>배송 요청사항:</th><td>${order.deliveryNotes || '-'}</td></tr>
                        <tr><th>주문일:</th><td>${formatDateTime(order.orderedAt || order.createdAt)}</td></tr>
                        <tr><th>배송예정일:</th><td>${order.expectedDeliveryDate ? formatDate(order.expectedDeliveryDate) : '-'}</td></tr>
                        <tr><th>배송완료일:</th><td>${order.deliveredAt ? formatDateTime(order.deliveredAt) : '-'}</td></tr>
                        <tr><th>수정일:</th><td>${order.updatedAt ? formatDateTime(order.updatedAt) : '-'}</td></tr>
                    </table>
                </div>
            </div>
            
            ${order.orderItems && order.orderItems.length > 0 ? `
                <div class="mt-3">
                    <h6>주문 상품</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>상품명</th>
                                    <th>수량</th>
                                    <th>단가</th>
                                    <th>소계</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${order.orderItems.map(item => `
                                    <tr>
                                        <td>${item.productName}</td>
                                        <td>${item.quantity}</td>
                                        <td>${formatCurrency(item.unitPrice)}</td>
                                        <td>${formatCurrency(item.quantity * item.unitPrice)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            ` : ''}
        `;
        
        showModal(`주문 상세 정보 - ${orderNumber}`, content);
        
    } catch (error) {
        console.error('주문 상세 정보 로드 실패:', error);
        showError('주문 정보를 불러오는데 실패했습니다.');
    }
}

// 유틸리티 함수들
function getOrderStatusBadgeColor(status) {
    switch (status) {
        case 'PENDING': return 'warning';
        case 'CONFIRMED': return 'info';
        case 'PROCESSING': return 'primary';
        case 'SHIPPED': return 'success';
        case 'DELIVERED': return 'success';
        case 'CANCELLED': return 'danger';
        case 'RETURNED': return 'secondary';
        default: return 'secondary';
    }
}

function getOrderStatusText(status) {
    switch (status) {
        case 'PENDING': return '주문확인';
        case 'CONFIRMED': return '주문승인';
        case 'PROCESSING': return '처리중';
        case 'SHIPPED': return '배송중';
        case 'DELIVERED': return '배송완료';
        case 'CANCELLED': return '취소';
        case 'RETURNED': return '반품';
        default: return status;
    }
}

function getPaymentMethodText(method) {
    switch (method) {
        case 'CREDIT_CARD': return '신용카드';
        case 'BANK_TRANSFER': return '계좌이체';
        case 'VIRTUAL_ACCOUNT': return '가상계좌';
        case 'MOBILE_PAYMENT': return '모바일결제';
        default: return method;
    }
}
