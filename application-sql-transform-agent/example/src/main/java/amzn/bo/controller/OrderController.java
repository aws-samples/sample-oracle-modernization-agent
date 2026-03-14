package amzn.bo.controller;

import amzn.bo.dto.ApiResponse;
import amzn.bo.dto.CancelOrderRequest;
import amzn.bo.dto.OrderAnalysisDto;
import amzn.bo.dto.OrderDto;
import amzn.bo.dto.PageResponse;
import amzn.bo.dto.RefundOrderRequest;
import amzn.bo.service.OrderService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 주문 관리 컨트롤러
 */
@Slf4j
@RestController
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderController {
    
    private final OrderService orderService;
    
    /**
     * 주문 목록 조회 (고급 분석 포함)
     */
    @GetMapping
    public ApiResponse<PageResponse<OrderAnalysisDto>> getOrderListWithAnalysis(
            @RequestParam(required = false) String searchKeyword,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String paymentMethod,
            @RequestParam(required = false) BigDecimal minAmount,
            @RequestParam(required = false) BigDecimal maxAmount,
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(required = false) String sortBy,
            @RequestParam(required = false) String sortDirection,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        
        try {
            OrderDto searchCondition = OrderDto.builder()
                    .searchKeyword(searchKeyword)
                    .statusFilter(status)
                    .paymentMethodFilter(paymentMethod)
                    .minAmount(minAmount)
                    .maxAmount(maxAmount)
                    .startDate(startDate)
                    .endDate(endDate)
                    .sortBy(sortBy)
                    .sortDirection(sortDirection)
                    .page(page)
                    .size(size)
                    .build();
            
            PageResponse<OrderAnalysisDto> result = orderService.getOrderListWithAnalysis(searchCondition);
            return ApiResponse.success(result);
            
        } catch (Exception e) {
            log.error("주문 목록 조회 중 오류 발생", e);
            return ApiResponse.error("주문 목록 조회에 실패했습니다.");
        }
    }
    
    /**
     * 주문 상세 정보 조회
     */
    @GetMapping("/{orderId}")
    public ApiResponse<OrderDto> getOrderDetail(@PathVariable Long orderId) {
        try {
            OrderDto order = orderService.getOrderDetail(orderId);
            return ApiResponse.success(order);
        } catch (Exception e) {
            log.error("주문 상세 정보 조회 중 오류 발생. orderId: {}", orderId, e);
            return ApiResponse.error("주문 정보를 찾을 수 없습니다.");
        }
    }
    
    /**
     * 주문 상태별 통계
     */
    @GetMapping("/statistics/status")
    public ApiResponse<List<Map<String, Object>>> getOrderStatusStatistics() {
        try {
            List<Map<String, Object>> stats = orderService.getOrderStatusStatistics();
            return ApiResponse.success(stats);
        } catch (Exception e) {
            log.error("주문 상태별 통계 조회 중 오류 발생", e);
            return ApiResponse.error("주문 상태별 통계 조회에 실패했습니다.");
        }
    }
    
    /**
     * 주문 트렌드 분석
     */
    @GetMapping("/analytics/trend")
    public ApiResponse<List<Map<String, Object>>> getOrderTrendAnalysis(
            @RequestParam String startDate,
            @RequestParam String endDate,
            @RequestParam(defaultValue = "DAY") String groupBy) {
        try {
            List<Map<String, Object>> trend = orderService.getOrderTrendAnalysis(startDate, endDate, groupBy);
            return ApiResponse.success(trend);
        } catch (Exception e) {
            log.error("주문 트렌드 분석 중 오류 발생", e);
            return ApiResponse.error("주문 트렌드 분석에 실패했습니다.");
        }
    }
    
    /**
     * 결제 방법별 주문 통계
     */
    @GetMapping("/statistics/payment-methods")
    public ApiResponse<List<Map<String, Object>>> getPaymentMethodStatistics() {
        try {
            List<Map<String, Object>> stats = orderService.getPaymentMethodStatistics();
            return ApiResponse.success(stats);
        } catch (Exception e) {
            log.error("결제 방법별 주문 통계 조회 중 오류 발생", e);
            return ApiResponse.error("결제 방법별 주문 통계 조회에 실패했습니다.");
        }
    }
    
    /**
     * 주문 처리 시간 분석
     */
    @GetMapping("/analytics/processing-time")
    public ApiResponse<List<Map<String, Object>>> getOrderProcessingTimeAnalysis() {
        try {
            List<Map<String, Object>> analysis = orderService.getOrderProcessingTimeAnalysis();
            return ApiResponse.success(analysis);
        } catch (Exception e) {
            log.error("주문 처리 시간 분석 중 오류 발생", e);
            return ApiResponse.error("주문 처리 시간 분석에 실패했습니다.");
        }
    }
    
    /**
     * 고객별 주문 패턴 분석
     */
    @GetMapping("/analytics/customer-pattern/{userId}")
    public ApiResponse<List<Map<String, Object>>> getCustomerOrderPatternAnalysis(@PathVariable Long userId) {
        try {
            List<Map<String, Object>> pattern = orderService.getCustomerOrderPatternAnalysis(userId);
            return ApiResponse.success(pattern);
        } catch (Exception e) {
            log.error("고객별 주문 패턴 분석 중 오류 발생. userId: {}", userId, e);
            return ApiResponse.error("고객별 주문 패턴 분석에 실패했습니다.");
        }
    }
    
    /**
     * 주문 아이템 상세 조회
     */
    @GetMapping("/{orderId}/items")
    public ApiResponse<List<Map<String, Object>>> getOrderItems(@PathVariable Long orderId) {
        try {
            List<Map<String, Object>> items = orderService.getOrderItems(orderId);
            return ApiResponse.success(items);
        } catch (Exception e) {
            log.error("주문 아이템 상세 조회 중 오류 발생. orderId: {}", orderId, e);
            return ApiResponse.error("주문 아이템 정보 조회에 실패했습니다.");
        }
    }
    
    /**
     * 주문 배송 정보 조회
     */
    @GetMapping("/{orderId}/shipping")
    public ApiResponse<Map<String, Object>> getOrderShippingInfo(@PathVariable Long orderId) {
        try {
            Map<String, Object> shippingInfo = orderService.getOrderShippingInfo(orderId);
            return ApiResponse.success(shippingInfo);
        } catch (Exception e) {
            log.error("주문 배송 정보 조회 중 오류 발생. orderId: {}", orderId, e);
            return ApiResponse.error("주문 배송 정보 조회에 실패했습니다.");
        }
    }
    
    /**
     * 주문 상태 업데이트
     */
    @PutMapping("/{orderId}/status")
    public ApiResponse<Void> updateOrderStatus(
            @PathVariable Long orderId,
            @RequestParam String status) {
        try {
            orderService.updateOrderStatus(orderId, status);
            return ApiResponse.success(null, "주문 상태가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("주문 상태 업데이트 중 오류 발생. orderId: {}, status: {}", orderId, status, e);
            return ApiResponse.error("주문 상태 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 주문 배송 정보 업데이트
     */
    @PutMapping("/{orderId}/shipping")
    public ApiResponse<Void> updateOrderShippingInfo(
            @PathVariable Long orderId,
            @RequestParam String trackingNumber,
            @RequestParam String carrier) {
        try {
            orderService.updateOrderShippingInfo(orderId, trackingNumber, carrier);
            return ApiResponse.success(null, "주문 배송 정보가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("주문 배송 정보 업데이트 중 오류 발생. orderId: {}", orderId, e);
            return ApiResponse.error("주문 배송 정보 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 주문 취소
     */
    @PutMapping("/{orderId}/cancel")
    public ApiResponse<Void> cancelOrder(
            @PathVariable Long orderId,
            @RequestBody CancelOrderRequest request) {
        try {
            orderService.cancelOrder(orderId, request.getReason());
            return ApiResponse.success(null, "주문이 성공적으로 취소되었습니다.");
        } catch (Exception e) {
            log.error("주문 취소 중 오류 발생. orderId: {}, reason: {}", orderId, request.getReason(), e);
            return ApiResponse.error("주문 취소에 실패했습니다.");
        }
    }
    
    /**
     * 주문 환불 처리
     */
    @PutMapping("/{orderId}/refund")
    public ApiResponse<Void> refundOrder(
            @PathVariable Long orderId,
            @RequestBody RefundOrderRequest request) {
        try {
            orderService.refundOrder(orderId, request.getReason(), request.getAmount(), request.getRefundType());
            return ApiResponse.success(null, "주문 환불이 성공적으로 처리되었습니다.");
        } catch (Exception e) {
            log.error("주문 환불 처리 중 오류 발생. orderId: {}, reason: {}", orderId, request.getReason(), e);
            return ApiResponse.error("주문 환불 처리에 실패했습니다: " + e.getMessage());
        }
    }
    
    /**
     * 주문 일괄 상태 업데이트
     */
    @PutMapping("/batch/status")
    public ApiResponse<Void> updateOrderStatusBatch(
            @RequestParam List<Long> orderIds,
            @RequestParam String status) {
        try {
            orderService.updateOrderStatusBatch(orderIds, status);
            return ApiResponse.success(null, "주문 일괄 상태 업데이트가 성공적으로 완료되었습니다.");
        } catch (Exception e) {
            log.error("주문 일괄 상태 업데이트 중 오류 발생. status: {}", status, e);
            return ApiResponse.error("주문 일괄 상태 업데이트에 실패했습니다.");
        }
    }
}
