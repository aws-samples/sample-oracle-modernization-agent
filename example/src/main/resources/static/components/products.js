// 상품 관리 관련 함수들
let currentProductsPage = 1;
let productsPageSize = 10;
let productsFilters = {};

// 상품 탭 로드
async function loadProductsTab() {
    showLoading('productsContent');
    
    const content = `
        <!-- 검색 및 필터 -->
        <div class="search-filters">
            <div class="row g-3">
                <div class="col-md-3">
                    <input type="text" class="form-control" id="productSearchKeyword" placeholder="상품명 검색">
                </div>
                <div class="col-md-2">
                    <input type="text" class="form-control" id="brandFilter" placeholder="브랜드">
                </div>
                <div class="col-md-2">
                    <input type="text" class="form-control" id="categoryFilter" placeholder="카테고리">
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="productSortBy">
                        <option value="createdAt">등록일순</option>
                        <option value="price">가격순</option>
                        <option value="stockQuantity">재고순</option>
                        <option value="averageRating">평점순</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <select class="form-select" id="productSortDirection">
                        <option value="DESC">내림차순</option>
                        <option value="ASC">오름차순</option>
                    </select>
                </div>
                <div class="col-md-1">
                    <button class="btn btn-primary w-100" onclick="searchProducts()">
                        <i class="fas fa-search"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- 상품 테이블 -->
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0"><i class="fas fa-box"></i> 상품 목록</h5>
                <div>
                    <select class="form-select form-select-sm d-inline-block w-auto" id="productsPageSize" onchange="changeProductsPageSize()">
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
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th>카테고리</th>
                                <th>가격</th>
                                <th>재고</th>
                                <th>평점</th>
                                <th>등록일</th>
                            </tr>
                        </thead>
                        <tbody id="productsTableBody">
                            <!-- 동적 컨텐츠 -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- 페이징 -->
        <nav class="mt-3">
            <ul class="pagination" id="productsPagination">
                <!-- 동적 컨텐츠 -->
            </ul>
        </nav>
    `;
    
    document.getElementById('productsContent').innerHTML = content;
    
    // 이벤트 리스너 추가
    document.getElementById('productSearchKeyword').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') searchProducts();
    });
    
    await loadProductsData();
}

// 상품 데이터 로드
async function loadProductsData() {
    try {
        console.log('Loading products data with filters:', productsFilters);
        
        const params = new URLSearchParams({
            page: currentProductsPage,
            size: productsPageSize,
            ...productsFilters
        });
        
        const url = `${API_BASE}/products?${params}`;
        console.log('Fetching URL:', url);
        
        const response = await fetch(url);
        const result = await response.json();
        console.log('Products API response:', result);
        
        // API 응답 구조 처리
        const data = result.data || result;
        
        renderProductsTable(data.content || []);
        renderProductsPagination(data);
        
    } catch (error) {
        console.error('상품 데이터 로드 실패:', error);
        document.getElementById('productsTableBody').innerHTML = `
            <tr><td colspan="8" class="text-center text-danger">데이터를 불러오는데 실패했습니다: ${error.message}</td></tr>
        `;
    }
}

// 상품 테이블 렌더링
function renderProductsTable(products) {
    const tbody = document.getElementById('productsTableBody');
    
    if (!products || products.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">데이터가 없습니다.</td></tr>';
        return;
    }
    
    tbody.innerHTML = products.map(product => {
        // 실제 API 응답 필드명 사용
        const brandName = product.brand || '-';
        const categoryName = product.categoryName || '-';
        const stockQuantity = product.stockQuantity || 0;
        
        return `
            <tr onclick="showProductDetail(${product.productId})">
                <td>${product.productId}</td>
                <td>${product.productName}</td>
                <td>${brandName}</td>
                <td>${categoryName}</td>
                <td>${formatCurrency(product.price)}</td>
                <td>
                    <span class="badge bg-${getStockBadgeColor(stockQuantity)}">
                        ${stockQuantity}
                    </span>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <span class="me-1">-</span>
                        <div class="text-muted">
                            <small>평점없음</small>
                        </div>
                    </div>
                </td>
                <td>${formatDate(product.createdAt)}</td>
            </tr>
        `;
    }).join('');
}

// 상품 페이징 렌더링
function renderProductsPagination(data) {
    const pagination = document.getElementById('productsPagination');
    const totalPages = data.totalPages || 1;
    const currentPage = data.page || currentProductsPage;
    
    let html = '';
    
    // 이전 버튼
    html += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="goToProductsPage(${currentPage - 1}); return false;">이전</a>
    </li>`;
    
    // 페이지 번호들
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<li class="page-item ${i === currentPage ? 'active' : ''}">
            <a class="page-link" href="#" onclick="goToProductsPage(${i}); return false;">${i}</a>
        </li>`;
    }
    
    // 다음 버튼
    html += `<li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="goToProductsPage(${currentPage + 1}); return false;">다음</a>
    </li>`;
    
    pagination.innerHTML = html;
}

// 상품 검색
function searchProducts() {
    const keyword = document.getElementById('productSearchKeyword').value.toLowerCase();
    const brand = document.getElementById('brandFilter').value.toLowerCase();
    const category = document.getElementById('categoryFilter').value.toLowerCase();
    
    console.log('Searching products:', { keyword, brand, category });
    
    // 테이블의 모든 행을 가져와서 필터링
    const tbody = document.getElementById('productsTableBody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 8) return; // 헤더나 빈 행 제외
        
        const productName = cells[1].textContent.toLowerCase();
        const productBrand = cells[2].textContent.toLowerCase();
        const productCategory = cells[3].textContent.toLowerCase();
        
        let show = true;
        
        // 키워드 검색 (상품명에서)
        if (keyword && !productName.includes(keyword)) {
            show = false;
        }
        
        // 브랜드 필터
        if (brand && !productBrand.includes(brand)) {
            show = false;
        }
        
        // 카테고리 필터
        if (category && !productCategory.includes(category)) {
            show = false;
        }
        
        row.style.display = show ? '' : 'none';
    });
}

// 상품 페이지 이동
function goToProductsPage(page) {
    console.log('Going to products page:', page);
    currentProductsPage = page;
    loadProductsData();
}

// 상품 페이지 크기 변경
function changeProductsPageSize() {
    productsPageSize = parseInt(document.getElementById('productsPageSize').value);
    currentProductsPage = 1;
    loadProductsData();
}

// 상품 상세 정보 표시
async function showProductDetail(productId) {
    try {
        const response = await fetch(`${API_BASE}/products/${productId}`);
        const result = await response.json();
        const product = result.data || result;
        
        // 실제 API 응답 필드명 사용
        const brandName = product.brand || '-';
        const categoryName = product.categoryName || '-';
        const stockQuantity = product.stockQuantity || 0;
        const description = product.description || '';
        
        const content = `
            <div class="row">
                <div class="col-md-6">
                    <h6>기본 정보</h6>
                    <table class="table table-sm">
                        <tr><th>상품 ID:</th><td>${product.productId}</td></tr>
                        <tr><th>상품명:</th><td>${product.productName}</td></tr>
                        <tr><th>SKU:</th><td>${product.sku || '-'}</td></tr>
                        <tr><th>브랜드:</th><td>${brandName}</td></tr>
                        <tr><th>카테고리:</th><td>${categoryName}</td></tr>
                        <tr><th>가격:</th><td>${formatCurrency(product.price)}</td></tr>
                        <tr><th>원가:</th><td>${product.costPrice ? formatCurrency(product.costPrice) : '-'}</td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6>재고 및 기타</h6>
                    <table class="table table-sm">
                        <tr><th>재고:</th><td><span class="badge bg-${getStockBadgeColor(stockQuantity)}">${stockQuantity}</span></td></tr>
                        <tr><th>최소재고:</th><td>${product.minStockLevel || '-'}</td></tr>
                        <tr><th>무게:</th><td>${product.weight || '-'}</td></tr>
                        <tr><th>크기:</th><td>${product.dimensions || '-'}</td></tr>
                        <tr><th>상태:</th><td>${product.status || 'ACTIVE'}</td></tr>
                        <tr><th>등록일:</th><td>${formatDate(product.createdAt)}</td></tr>
                        <tr><th>수정일:</th><td>${product.updatedAt ? formatDate(product.updatedAt) : '-'}</td></tr>
                    </table>
                </div>
            </div>
            ${description ? `
                <div class="mt-3">
                    <h6>상품 설명</h6>
                    <p class="text-muted">${description}</p>
                </div>
            ` : ''}
        `;
        
        showModal(`상품 상세 정보 - ${product.productName}`, content);
        
    } catch (error) {
        console.error('상품 상세 정보 로드 실패:', error);
        showError('상품 정보를 불러오는데 실패했습니다.');
    }
}

// 유틸리티 함수들
function getStockBadgeColor(stock) {
    if (stock <= 0) return 'danger';
    if (stock <= 10) return 'warning';
    return 'success';
}

function renderStars(rating) {
    const fullStars = Math.floor(rating);
    const hasHalfStar = rating % 1 >= 0.5;
    const emptyStars = 5 - fullStars - (hasHalfStar ? 1 : 0);
    
    let stars = '';
    
    // 꽉 찬 별
    for (let i = 0; i < fullStars; i++) {
        stars += '<i class="fas fa-star"></i>';
    }
    
    // 반 별
    if (hasHalfStar) {
        stars += '<i class="fas fa-star-half-alt"></i>';
    }
    
    // 빈 별
    for (let i = 0; i < emptyStars; i++) {
        stars += '<i class="far fa-star"></i>';
    }
    
    return stars;
}
