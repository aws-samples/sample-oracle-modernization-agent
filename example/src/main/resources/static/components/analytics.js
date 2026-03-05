// Analytics 탭 로드
function loadAnalyticsTab() {
    console.log('Loading analytics tab...');
    
    const content = `
        <div class="container-fluid">
            <div class="row mb-4">
                <div class="col-12">
                    <h4><i class="fas fa-chart-line"></i> 분석 리포트</h4>
                    <p class="text-muted">고급 분석 기능을 통해 비즈니스 인사이트를 확인하세요.</p>
                </div>
            </div>

            <!-- 분석 메뉴 -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-outline-primary active" onclick="loadSalesDashboard()">매출 대시보드</button>
                        <button type="button" class="btn btn-outline-primary" onclick="loadRevenueTrend()">매출 트렌드</button>
                        <button type="button" class="btn btn-outline-primary" onclick="loadProductAnalysis()">상품 분석</button>
                        <button type="button" class="btn btn-outline-primary" onclick="loadCustomerAnalysis()">고객 분석</button>
                        <button type="button" class="btn btn-outline-primary" onclick="loadPatternAnalysis()">패턴 분석</button>
                    </div>
                </div>
            </div>

            <!-- 분석 컨텐츠 -->
            <div id="analyticsData">
                <div class="text-center">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2">분석 데이터를 로드하고 있습니다...</p>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('analyticsContent').innerHTML = content;
    
    // 기본으로 매출 대시보드 로드
    setTimeout(() => {
        loadSalesDashboard();
    }, 100);
}

// 매출 대시보드
async function loadSalesDashboard() {
    try {
        setActiveAnalyticsButton(0);
        
        const response = await fetch(`${API_BASE}/analytics/sales-dashboard`);
        const result = await response.json();
        
        if (result.success) {
            renderSalesDashboard(result.data);
        } else {
            showAnalyticsError('매출 대시보드 데이터를 불러올 수 없습니다.');
        }
    } catch (error) {
        console.error('Sales dashboard error:', error);
        showAnalyticsError('매출 대시보드 로드 중 오류가 발생했습니다.');
    }
}

// 매출 트렌드
async function loadRevenueTrend() {
    try {
        setActiveAnalyticsButton(1);
        
        const response = await fetch(`${API_BASE}/analytics/revenue-trend?groupBy=MONTH`);
        const result = await response.json();
        
        if (result.success) {
            renderRevenueTrend(result.data);
        } else {
            showAnalyticsError('매출 트렌드 데이터를 불러올 수 없습니다.');
        }
    } catch (error) {
        console.error('Revenue trend error:', error);
        showAnalyticsError('매출 트렌드 로드 중 오류가 발생했습니다.');
    }
}

// 상품 분석
async function loadProductAnalysis() {
    try {
        setActiveAnalyticsButton(2);
        
        const [productResponse, categoryResponse] = await Promise.all([
            fetch(`${API_BASE}/analytics/product-revenue?limit=10`),
            fetch(`${API_BASE}/analytics/category-revenue`)
        ]);
        
        const productResult = await productResponse.json();
        const categoryResult = await categoryResponse.json();
        
        if (productResult.success && categoryResult.success) {
            renderProductAnalysis(productResult.data, categoryResult.data);
        } else {
            showAnalyticsError('상품 분석 데이터를 불러올 수 없습니다.');
        }
    } catch (error) {
        console.error('Product analysis error:', error);
        showAnalyticsError('상품 분석 로드 중 오류가 발생했습니다.');
    }
}

// 고객 분석
async function loadCustomerAnalysis() {
    try {
        setActiveAnalyticsButton(3);
        
        const [segmentResponse, rfmResponse] = await Promise.all([
            fetch(`${API_BASE}/analytics/customer-segment`),
            fetch(`${API_BASE}/analytics/rfm-analysis`)
        ]);
        
        const segmentResult = await segmentResponse.json();
        const rfmResult = await rfmResponse.json();
        
        if (segmentResult.success && rfmResult.success) {
            renderCustomerAnalysis(segmentResult.data, rfmResult.data);
        } else {
            showAnalyticsError('고객 분석 데이터를 불러올 수 없습니다.');
        }
    } catch (error) {
        console.error('Customer analysis error:', error);
        showAnalyticsError('고객 분석 로드 중 오류가 발생했습니다.');
    }
}

// 패턴 분석
async function loadPatternAnalysis() {
    try {
        setActiveAnalyticsButton(4);
        
        const [hourlyResponse, weeklyResponse] = await Promise.all([
            fetch(`${API_BASE}/analytics/hourly-pattern`),
            fetch(`${API_BASE}/analytics/weekly-pattern`)
        ]);
        
        const hourlyResult = await hourlyResponse.json();
        const weeklyResult = await weeklyResponse.json();
        
        if (hourlyResult.success && weeklyResult.success) {
            renderPatternAnalysis(hourlyResult.data, weeklyResult.data);
        } else {
            showAnalyticsError('패턴 분석 데이터를 불러올 수 없습니다.');
        }
    } catch (error) {
        console.error('Pattern analysis error:', error);
        showAnalyticsError('패턴 분석 로드 중 오류가 발생했습니다.');
    }
}

// 매출 대시보드 렌더링
function renderSalesDashboard(data) {
    const content = `
        <div class="row">
            <div class="col-12">
                <h5>매출 대시보드</h5>
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>기간</th>
                                <th>카테고리</th>
                                <th>결제방법</th>
                                <th>주문수</th>
                                <th>총매출</th>
                                <th>평균주문액</th>
                                <th>판매수량</th>
                                <th>고유고객수</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.map(item => `
                                <tr>
                                    <td>${item.TIME_PERIOD || '-'}</td>
                                    <td>${item.CATEGORY_NAME || '-'}</td>
                                    <td>${item.PAYMENT_METHOD || '-'}</td>
                                    <td>${item.ORDER_COUNT || 0}</td>
                                    <td>${formatCurrency(item.TOTAL_REVENUE || 0)}</td>
                                    <td>${formatCurrency(item.AVG_ORDER_VALUE || 0)}</td>
                                    <td>${item.TOTAL_QUANTITY_SOLD || 0}</td>
                                    <td>${item.UNIQUE_CUSTOMERS || 0}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('analyticsData').innerHTML = content;
}

// 매출 트렌드 렌더링
function renderRevenueTrend(data) {
    const content = `
        <div class="row">
            <div class="col-12">
                <h5>매출 트렌드</h5>
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>기간</th>
                                <th>총매출</th>
                                <th>주문수</th>
                                <th>평균주문액</th>
                                <th>고유고객수</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.map(item => `
                                <tr>
                                    <td>${item.TIME_PERIOD || '-'}</td>
                                    <td>${formatCurrency(item.TOTAL_REVENUE || 0)}</td>
                                    <td>${item.ORDER_COUNT || 0}</td>
                                    <td>${formatCurrency(item.AVG_ORDER_VALUE || 0)}</td>
                                    <td>${item.UNIQUE_CUSTOMERS || 0}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('analyticsData').innerHTML = content;
}

// 상품 분석 렌더링
function renderProductAnalysis(productData, categoryData) {
    const content = `
        <div class="row">
            <div class="col-md-6">
                <h5>상위 상품 매출</h5>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>상품명</th>
                                <th>매출</th>
                                <th>판매량</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${productData.map(item => `
                                <tr>
                                    <td>${item.PRODUCT_NAME || '-'}</td>
                                    <td>${formatCurrency(item.TOTAL_REVENUE || 0)}</td>
                                    <td>${item.TOTAL_QUANTITY || 0}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="col-md-6">
                <h5>카테고리별 매출</h5>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>카테고리</th>
                                <th>매출</th>
                                <th>점유율</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${categoryData.map(item => `
                                <tr>
                                    <td>${item.CATEGORY_NAME || '-'}</td>
                                    <td>${formatCurrency(item.TOTAL_REVENUE || 0)}</td>
                                    <td>${item.REVENUE_SHARE ? item.REVENUE_SHARE + '%' : '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('analyticsData').innerHTML = content;
}

// 고객 분석 렌더링
function renderCustomerAnalysis(segmentData, rfmData) {
    const content = `
        <div class="row">
            <div class="col-md-6">
                <h5>고객 세그먼트</h5>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>세그먼트</th>
                                <th>고객수</th>
                                <th>평균매출</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${segmentData.map(item => `
                                <tr>
                                    <td>${item.CUSTOMER_SEGMENT || '-'}</td>
                                    <td>${item.CUSTOMER_COUNT || 0}</td>
                                    <td>${formatCurrency(item.AVG_REVENUE || 0)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="col-md-6">
                <h5>RFM 분석 (상위 10명)</h5>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>고객ID</th>
                                <th>R점수</th>
                                <th>F점수</th>
                                <th>M점수</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rfmData.slice(0, 10).map(item => `
                                <tr>
                                    <td>${item.USER_ID || '-'}</td>
                                    <td>${item.RECENCY_SCORE || 0}</td>
                                    <td>${item.FREQUENCY_SCORE || 0}</td>
                                    <td>${item.MONETARY_SCORE || 0}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('analyticsData').innerHTML = content;
}

// 패턴 분석 렌더링
function renderPatternAnalysis(hourlyData, weeklyData) {
    const content = `
        <div class="row">
            <div class="col-md-6">
                <h5>시간대별 주문 패턴</h5>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>시간</th>
                                <th>주문수</th>
                                <th>평균매출</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${hourlyData.map(item => `
                                <tr>
                                    <td>${item.HOUR_OF_DAY || 0}시</td>
                                    <td>${item.ORDER_COUNT || 0}</td>
                                    <td>${formatCurrency(item.AVG_ORDER_VALUE || 0)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="col-md-6">
                <h5>요일별 주문 패턴</h5>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>요일</th>
                                <th>주문수</th>
                                <th>평균매출</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${weeklyData.map(item => `
                                <tr>
                                    <td>${item.DAY_OF_WEEK || '-'}</td>
                                    <td>${item.ORDER_COUNT || 0}</td>
                                    <td>${formatCurrency(item.AVG_ORDER_VALUE || 0)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('analyticsData').innerHTML = content;
}

// 활성 버튼 설정
function setActiveAnalyticsButton(index) {
    const buttons = document.querySelectorAll('#analyticsContent .btn-group .btn');
    buttons.forEach((btn, i) => {
        if (i === index) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

// 에러 표시
function showAnalyticsError(message) {
    const content = `
        <div class="alert alert-danger" role="alert">
            <i class="fas fa-exclamation-triangle"></i> ${message}
        </div>
    `;
    
    document.getElementById('analyticsData').innerHTML = content;
}
