package amzn.bo.service;

import amzn.bo.dto.OrderAnalysisDto;
import amzn.bo.dto.OrderDto;
import amzn.bo.dto.PageResponse;
import amzn.bo.mapper.OrderMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 주문 서비스
 */
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class OrderService {
    
    private final OrderMapper orderMapper;
    
    /**
     * 주문 목록 조회 (페이징, 고급 분석)
     */
    public PageResponse<OrderAnalysisDto> getOrderListWithAnalysis(OrderDto searchCondition) {
        Map<String, Object> params = buildSearchParams(searchCondition);
        
        // 페이징 처리
        int page = searchCondition.getPage() != null ? searchCondition.getPage() : 0;
        int size = searchCondition.getSize() != null ? searchCondition.getSize() : 20;
        int offset = page * size;
        
        params.put("offset", offset);
        params.put("limit", size);
        
        List<OrderAnalysisDto> orders = orderMapper.selectOrderListWithAnalysis(params);
        long totalCount = orderMapper.selectOrderCount(params);
        
        return PageResponse.of(orders, page, size, totalCount);
    }
    
    /**
     * 주문 상세 정보 조회
     */
    public OrderDto getOrderDetail(Long orderId) {
        OrderDto order = orderMapper.selectOrderDetail(orderId);
        if (order == null) {
            throw new RuntimeException("주문을 찾을 수 없습니다. ID: " + orderId);
        }
        return order;
    }
    
    /**
     * 주문 상태별 통계
     */
    public List<Map<String, Object>> getOrderStatusStatistics() {
        return orderMapper.selectOrderStatusStatistics();
    }
    
    /**
     * 주문 트렌드 분석
     */
    public List<Map<String, Object>> getOrderTrendAnalysis(String startDate, String endDate, String groupBy) {
        return orderMapper.selectOrderTrendAnalysis(startDate, endDate, groupBy);
    }
    
    /**
     * 결제 방법별 주문 통계
     */
    public List<Map<String, Object>> getPaymentMethodStatistics() {
        return orderMapper.selectPaymentMethodStatistics();
    }
    
    /**
     * 주문 처리 시간 분석
     */
    public List<Map<String, Object>> getOrderProcessingTimeAnalysis() {
        return orderMapper.selectOrderProcessingTimeAnalysis();
    }
    
    /**
     * 고객별 주문 패턴 분석
     */
    public List<Map<String, Object>> getCustomerOrderPatternAnalysis(Long userId) {
        // 기존 selectOrderListWithAnalysis 매퍼를 활용하여 고객 주문 패턴 분석
        Map<String, Object> params = new HashMap<>();
        params.put("userId", userId);
        params.put("page", 0);
        params.put("size", 100);
        
        List<OrderAnalysisDto> orders = orderMapper.selectOrderListWithAnalysis(params);
        
        if (orders.isEmpty()) {
            return List.of();
        }
        
        // 주문 패턴 분석 결과를 Map으로 변환
        Map<String, Object> pattern = new HashMap<>();
        pattern.put("USER_ID", userId);
        pattern.put("TOTAL_ORDERS", orders.size());
        pattern.put("TOTAL_SPENT", orders.stream().mapToDouble(o -> o.getTotalAmount().doubleValue()).sum());
        pattern.put("AVG_ORDER_VALUE", orders.stream().mapToDouble(o -> o.getTotalAmount().doubleValue()).average().orElse(0));
        pattern.put("FIRST_ORDER_DATE", orders.get(orders.size() - 1).getOrderedAt());
        pattern.put("LAST_ORDER_DATE", orders.get(0).getOrderedAt());
        pattern.put("PREFERRED_PAYMENT_METHOD", orders.get(0).getPaymentMethod());
        
        return List.of(pattern);
    }
    
    /**
     * 주문 아이템 상세 조회
     */
    public List<Map<String, Object>> getOrderItems(Long orderId) {
        // 기존 selectOrderListWithAnalysis 매퍼를 활용하여 주문 정보 조회
        Map<String, Object> params = new HashMap<>();
        params.put("orderId", orderId);
        params.put("page", 0);
        params.put("size", 1);
        
        List<OrderAnalysisDto> orders = orderMapper.selectOrderListWithAnalysis(params);
        if (orders.isEmpty()) {
            return List.of(); // 빈 리스트 반환
        }
        
        OrderAnalysisDto order = orders.get(0);
        
        // 주문 아이템 정보를 Map으로 변환
        Map<String, Object> item = new HashMap<>();
        item.put("ORDER_ID", order.getOrderId());
        item.put("ORDER_NUMBER", order.getOrderNumber());
        item.put("ITEM_COUNT", order.getItemCount());
        item.put("UNIQUE_PRODUCTS", order.getUniqueProducts());
        item.put("AVG_ITEM_PRICE", order.getAvgItemPrice());
        item.put("TOTAL_AMOUNT", order.getTotalAmount());
        
        return List.of(item);
    }
    
    /**
     * 주문 배송 정보 조회
     */
    public Map<String, Object> getOrderShippingInfo(Long orderId) {
        Map<String, Object> shippingInfo = orderMapper.selectOrderShippingInfo(orderId);
        if (shippingInfo == null) {
            throw new RuntimeException("주문 배송 정보를 찾을 수 없습니다. ID: " + orderId);
        }
        return shippingInfo;
    }
    
    /**
     * 주문 상태 업데이트
     */
    @Transactional
    public void updateOrderStatus(Long orderId, String status) {
        int result = orderMapper.updateOrderStatus(orderId, status);
        if (result == 0) {
            throw new RuntimeException("주문 상태 업데이트에 실패했습니다. ID: " + orderId);
        }
        log.info("주문 상태 업데이트 완료. ID: {}, Status: {}", orderId, status);
    }
    
    /**
     * 주문 배송 정보 업데이트
     */
    @Transactional
    public void updateOrderShippingInfo(Long orderId, String trackingNumber, String carrier) {
        int result = orderMapper.updateOrderShippingInfo(orderId, trackingNumber, carrier);
        if (result == 0) {
            throw new RuntimeException("주문 배송 정보 업데이트에 실패했습니다. ID: " + orderId);
        }
        log.info("주문 배송 정보 업데이트 완료. ID: {}, Tracking: {}, Carrier: {}", orderId, trackingNumber, carrier);
    }
    
    /**
     * 주문 취소
     */
    @Transactional
    public void cancelOrder(Long orderId, String reason) {
        int result = orderMapper.cancelOrder(orderId, reason);
        if (result == 0) {
            throw new RuntimeException("주문 취소에 실패했습니다. ID: " + orderId);
        }
        log.info("주문 취소 완료. ID: {}, Reason: {}", orderId, reason);
    }
    
    /**
     * 주문 환불 처리
     */
    @Transactional
    public void refundOrder(Long orderId, String reason, BigDecimal refundAmount, String refundType) {
        // 1. 주문 정보 조회
        OrderDto order = getOrderDetail(orderId);
        if (order == null) {
            throw new RuntimeException("주문을 찾을 수 없습니다. ID: " + orderId);
        }
        
        // 2. 환불 가능 상태 검증
        if (!isRefundableStatus(order.getOrderStatus())) {
            throw new RuntimeException("현재 주문 상태에서는 환불이 불가능합니다. 상태: " + order.getOrderStatus());
        }
        
        // 3. 환불 금액 검증
        if (refundAmount != null && refundAmount.compareTo(order.getTotalAmount()) > 0) {
            throw new RuntimeException("환불 금액이 주문 금액을 초과할 수 없습니다.");
        }
        
        // 4. 환불 처리
        Map<String, Object> params = new HashMap<>();
        params.put("orderId", orderId);
        params.put("reason", reason);
        params.put("refundAmount", refundAmount != null ? refundAmount : order.getTotalAmount());
        params.put("refundType", refundType != null ? refundType : "FULL");
        
        int result = orderMapper.refundOrder(params);
        if (result == 0) {
            throw new RuntimeException("주문 환불 처리에 실패했습니다. ID: " + orderId);
        }
        
        log.info("주문 환불 처리 완료. ID: {}, Reason: {}, Amount: {}, Type: {}", 
                orderId, reason, refundAmount, refundType);
    }
    
    /**
     * 환불 가능 상태 확인
     */
    private boolean isRefundableStatus(String orderStatus) {
        return "DELIVERED".equals(orderStatus) || 
               "SHIPPED".equals(orderStatus) || 
               "PROCESSING".equals(orderStatus);
    }
    
    /**
     * 주문 일괄 상태 업데이트
     */
    @Transactional
    public void updateOrderStatusBatch(List<Long> orderIds, String status) {
        int result = orderMapper.updateOrderStatusBatch(orderIds, status);
        if (result == 0) {
            throw new RuntimeException("주문 일괄 상태 업데이트에 실패했습니다.");
        }
        log.info("주문 일괄 상태 업데이트 완료. Count: {}, Status: {}", result, status);
    }
    
    /**
     * 검색 조건 파라미터 빌드
     */
    private Map<String, Object> buildSearchParams(OrderDto searchCondition) {
        Map<String, Object> params = new HashMap<>();
        
        if (searchCondition.getSearchKeyword() != null && !searchCondition.getSearchKeyword().trim().isEmpty()) {
            params.put("searchKeyword", searchCondition.getSearchKeyword().trim());
        }
        
        if (searchCondition.getStatusFilter() != null && !searchCondition.getStatusFilter().trim().isEmpty()) {
            params.put("orderStatus", searchCondition.getStatusFilter().trim());
        }
        
        if (searchCondition.getPaymentMethodFilter() != null && !searchCondition.getPaymentMethodFilter().trim().isEmpty()) {
            params.put("paymentMethod", searchCondition.getPaymentMethodFilter().trim());
        }
        
        if (searchCondition.getMinAmount() != null) {
            params.put("minAmount", searchCondition.getMinAmount());
        }
        
        if (searchCondition.getMaxAmount() != null) {
            params.put("maxAmount", searchCondition.getMaxAmount());
        }
        
        if (searchCondition.getStartDate() != null && !searchCondition.getStartDate().trim().isEmpty()) {
            params.put("startDate", searchCondition.getStartDate().trim());
        }
        
        if (searchCondition.getEndDate() != null && !searchCondition.getEndDate().trim().isEmpty()) {
            params.put("endDate", searchCondition.getEndDate().trim());
        }
        
        // 정렬 조건
        String sortBy = searchCondition.getSortBy() != null ? searchCondition.getSortBy() : "ORDERED_AT";
        String sortDirection = searchCondition.getSortDirection() != null ? searchCondition.getSortDirection() : "DESC";
        params.put("sortBy", sortBy);
        params.put("sortDirection", sortDirection);
        
        return params;
    }
}
