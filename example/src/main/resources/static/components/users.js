// 사용자 관리 관련 함수들
let currentUsersPage = 1;
let usersPageSize = 10;
let usersFilters = {};

// 사용자 탭 로드
async function loadUsersTab() {
    showLoading('usersContent');
    
    const content = `
        <!-- 검색 및 필터 -->
        <div class="search-filters">
            <div class="row g-3">
                <div class="col-md-2">
                    <input type="text" class="form-control" id="userSearchKeyword" placeholder="이름 또는 이메일 검색">
                </div>
                <div class="col-md-2">
                    <input type="date" class="form-control" id="userStartDate" title="가입일 시작">
                </div>
                <div class="col-md-2">
                    <input type="date" class="form-control" id="userEndDate" title="가입일 종료">
                </div>
                <div class="col-md-1">
                    <select class="form-select" id="userGradeFilter">
                        <option value="">전체등급</option>
                        <option value="VIP">VIP</option>
                        <option value="PREMIUM">PREMIUM</option>
                        <option value="REGULAR">REGULAR</option>
                        <option value="NEW">NEW</option>
                    </select>
                </div>
                <div class="col-md-1">
                    <select class="form-select" id="userStatusFilter">
                        <option value="">전체상태</option>
                        <option value="ACTIVE">활성</option>
                        <option value="INACTIVE">비활성</option>
                        <option value="SUSPENDED">정지</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="userSortBy">
                        <option value="createdAt">가입일순</option>
                        <option value="totalSpent">구매액순</option>
                        <option value="orderCount">주문수순</option>
                    </select>
                </div>
                <div class="col-md-1">
                    <select class="form-select" id="userSortDirection">
                        <option value="DESC">내림차순</option>
                        <option value="ASC">오름차순</option>
                    </select>
                </div>
                <div class="col-md-1">
                    <button class="btn btn-primary w-100" onclick="searchUsers()">
                        <i class="fas fa-search"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- 사용자 테이블 -->
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0"><i class="fas fa-users"></i> 사용자 목록</h5>
                <div>
                    <select class="form-select form-select-sm d-inline-block w-auto" id="usersPageSize" onchange="changeUsersPageSize()">
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
                                <th>ID</th>
                                <th>이름</th>
                                <th>이메일</th>
                                <th>등급</th>
                                <th>상태</th>
                                <th>주문수</th>
                                <th>총구매액</th>
                                <th>가입일</th>
                            </tr>
                        </thead>
                        <tbody id="usersTableBody">
                            <!-- 동적 컨텐츠 -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- 페이징 -->
        <nav class="mt-3">
            <ul class="pagination" id="usersPagination">
                <!-- 동적 컨텐츠 -->
            </ul>
        </nav>
    `;
    
    document.getElementById('usersContent').innerHTML = content;
    
    // 실제 데이터 범위로 날짜 필터 초기화
    document.getElementById('userStartDate').value = '2024-08-01';
    document.getElementById('userEndDate').value = '2025-08-31';
    
    // 이벤트 리스너 추가
    document.getElementById('userSearchKeyword').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') searchUsers();
    });
    
    await loadUsersData();
}

// 사용자 데이터 로드
async function loadUsersData() {
    try {
        console.log('Loading users data with filters:', usersFilters);
        
        const params = new URLSearchParams({
            page: currentUsersPage,
            size: usersPageSize,
            ...usersFilters
        });
        
        const url = `${API_BASE}/users?${params}`;
        console.log('Fetching URL:', url);
        
        const response = await fetch(url);
        const result = await response.json();
        console.log('Users API response:', result);
        
        // API 응답 구조 처리
        const data = result.data || result;
        
        renderUsersTable(data.content || []);
        renderUsersPagination(data);
        
    } catch (error) {
        console.error('사용자 데이터 로드 실패:', error);
        document.getElementById('usersTableBody').innerHTML = `
            <tr><td colspan="8" class="text-center text-danger">데이터를 불러오는데 실패했습니다: ${error.message}</td></tr>
        `;
    }
}

// 사용자 테이블 렌더링
function renderUsersTable(users) {
    const tbody = document.getElementById('usersTableBody');
    
    if (!users || users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">데이터가 없습니다.</td></tr>';
        return;
    }
    
    tbody.innerHTML = users.map(user => {
        // API 응답 필드명 매핑
        const userName = user.userName || `${user.firstName || ''} ${user.lastName || ''}`.trim() || user.email;
        const userGrade = user.userGrade || 'NEW';
        const status = user.status || 'ACTIVE';
        const orderCount = user.orderCount || 0;
        const totalSpent = user.totalSpent || 0;
        
        return `
            <tr onclick="showUserDetail(${user.userId})">
                <td>${user.userId}</td>
                <td>${userName}</td>
                <td>${user.email}</td>
                <td><span class="badge bg-${getGradeBadgeColor(userGrade)}">${userGrade}</span></td>
                <td><span class="badge bg-${getStatusBadgeColor(status)}">${getStatusText(status)}</span></td>
                <td>${orderCount}</td>
                <td>${formatCurrency(totalSpent)}</td>
                <td>${formatDate(user.createdAt)}</td>
            </tr>
        `;
    }).join('');
}

// 사용자 페이징 렌더링
function renderUsersPagination(data) {
    const pagination = document.getElementById('usersPagination');
    const totalPages = data.totalPages || 1;
    const currentPage = data.page || currentUsersPage; // API 응답의 page 사용
    
    let html = '';
    
    // 이전 버튼
    html += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="goToUsersPage(${currentPage - 1}); return false;">이전</a>
    </li>`;
    
    // 페이지 번호들
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<li class="page-item ${i === currentPage ? 'active' : ''}">
            <a class="page-link" href="#" onclick="goToUsersPage(${i}); return false;">${i}</a>
        </li>`;
    }
    
    // 다음 버튼
    html += `<li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="goToUsersPage(${currentPage + 1}); return false;">다음</a>
    </li>`;
    
    pagination.innerHTML = html;
    
    console.log('Pagination rendered:', { currentPage, totalPages, startPage, endPage });
}

// 사용자 검색
function searchUsers() {
    const keyword = document.getElementById('userSearchKeyword').value.toLowerCase();
    const grade = document.getElementById('userGradeFilter').value;
    const status = document.getElementById('userStatusFilter').value;
    
    console.log('Searching users:', { keyword, grade, status });
    
    // 테이블의 모든 행을 가져와서 필터링
    const tbody = document.getElementById('usersTableBody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 8) return; // 헤더나 빈 행 제외
        
        const email = cells[2].textContent.toLowerCase();
        const userName = cells[1].textContent.toLowerCase();
        const userGrade = cells[3].textContent.trim();
        const userStatus = cells[4].textContent.trim();
        
        let show = true;
        
        // 키워드 검색
        if (keyword && !email.includes(keyword) && !userName.includes(keyword)) {
            show = false;
        }
        
        // 등급 필터
        if (grade && !userGrade.includes(grade)) {
            show = false;
        }
        
        // 상태 필터
        if (status && !userStatus.includes(status)) {
            show = false;
        }
        
        row.style.display = show ? '' : 'none';
    });
}

// 사용자 페이지 이동
function goToUsersPage(page) {
    console.log('Going to users page:', page);
    currentUsersPage = page;
    loadUsersData();
}

// 사용자 페이지 크기 변경
function changeUsersPageSize() {
    usersPageSize = parseInt(document.getElementById('usersPageSize').value);
    currentUsersPage = 1;
    loadUsersData();
}

// 사용자 상세 정보 표시
async function showUserDetail(userId) {
    try {
        const response = await fetch(`${API_BASE}/users/${userId}`);
        const result = await response.json();
        const user = result.data || result;
        
        // 실제 API 응답 필드명 사용
        const userName = `${user.firstName || ''} ${user.lastName || ''}`.trim() || user.email;
        const userGrade = user.userGrade || 'NEW';
        const status = user.status || 'ACTIVE';
        const orderCount = user.orderCount || 0;
        const totalSpent = user.totalSpent || 0;
        const phoneNumber = user.phone || '-';
        const avgOrderValue = user.avgOrderValue || 0;
        
        const content = `
            <div class="row">
                <div class="col-md-6">
                    <h6>기본 정보</h6>
                    <table class="table table-sm">
                        <tr><th>사용자 ID:</th><td>${user.userId}</td></tr>
                        <tr><th>이름:</th><td>${userName}</td></tr>
                        <tr><th>이메일:</th><td>${user.email}</td></tr>
                        <tr><th>전화번호:</th><td>${phoneNumber}</td></tr>
                        <tr><th>등급:</th><td><span class="badge bg-${getGradeBadgeColor(userGrade)}">${userGrade}</span></td></tr>
                        <tr><th>상태:</th><td><span class="badge bg-${getStatusBadgeColor(status)}">${getStatusText(status)}</span></td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6>활동 통계</h6>
                    <table class="table table-sm">
                        <tr><th>총 주문수:</th><td>${orderCount}건</td></tr>
                        <tr><th>총 구매액:</th><td>${formatCurrency(totalSpent)}</td></tr>
                        <tr><th>평균 주문액:</th><td>${formatCurrency(avgOrderValue)}</td></tr>
                        <tr><th>지출 순위:</th><td>${user.spendingRank || '-'}위</td></tr>
                        <tr><th>가입일:</th><td>${formatDate(user.createdAt)}</td></tr>
                        <tr><th>최근 수정:</th><td>${user.updatedAt ? formatDate(user.updatedAt) : '-'}</td></tr>
                    </table>
                </div>
            </div>
        `;
        
        showModal(`사용자 상세 정보 - ${userName}`, content);
        
    } catch (error) {
        console.error('사용자 상세 정보 로드 실패:', error);
        showError('사용자 정보를 불러오는데 실패했습니다.');
    }
}

// 유틸리티 함수들
function getGradeBadgeColor(grade) {
    switch (grade) {
        case 'VIP': return 'danger';
        case 'PREMIUM': return 'warning';
        case 'NEW': return 'success';
        default: return 'secondary';
    }
}

function getStatusBadgeColor(status) {
    switch (status) {
        case 'ACTIVE': return 'success';
        case 'INACTIVE': return 'secondary';
        case 'SUSPENDED': return 'danger';
        default: return 'secondary';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'ACTIVE': return '활성';
        case 'INACTIVE': return '비활성';
        case 'SUSPENDED': return '정지';
        default: return status;
    }
}
