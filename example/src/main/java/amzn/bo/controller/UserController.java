package amzn.bo.controller;

import amzn.bo.dto.ApiResponse;
import amzn.bo.dto.PageResponse;
import amzn.bo.dto.UserDto;
import amzn.bo.service.UserService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 사용자 관리 컨트롤러
 */
@Slf4j
@RestController
@RequestMapping("/api/users")
@RequiredArgsConstructor
public class UserController {
    
    private final UserService userService;
    
    /**
     * 사용자 목록 조회
     */
    @GetMapping
    public ApiResponse<PageResponse<UserDto>> getUserList(
            @RequestParam(required = false) String email,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String userGrade,
            @RequestParam(required = false) Integer minOrderCount,
            @RequestParam(required = false) String minTotalSpent,
            @RequestParam(required = false) String searchKeyword,
            @RequestParam(required = false) String sortBy,
            @RequestParam(required = false) String sortDirection,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        
        try {
            UserDto searchCondition = UserDto.builder()
                    .email(email)
                    .status(status)
                    .userGradeFilter(userGrade)
                    .minOrderCount(minOrderCount)
                    .searchKeyword(searchKeyword)
                    .sortBy(sortBy)
                    .sortDirection(sortDirection)
                    .page(page)
                    .size(size)
                    .build();
            
            PageResponse<UserDto> result = userService.getUserList(searchCondition);
            return ApiResponse.success(result);
            
        } catch (Exception e) {
            log.error("사용자 목록 조회 중 오류 발생", e);
            return ApiResponse.error("사용자 목록 조회에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 상세 정보 조회
     */
    @GetMapping("/{userId}")
    public ApiResponse<UserDto> getUserDetail(@PathVariable Long userId) {
        try {
            UserDto user = userService.getUserDetail(userId);
            return ApiResponse.success(user);
        } catch (Exception e) {
            log.error("사용자 상세 정보 조회 중 오류 발생. userId: {}", userId, e);
            return ApiResponse.error("사용자 정보를 찾을 수 없습니다.");
        }
    }
    
    /**
     * 사용자 활동 통계 조회
     */
    @GetMapping("/{userId}/activity-stats")
    public ApiResponse<Map<String, Object>> getUserActivityStats(@PathVariable Long userId) {
        try {
            Map<String, Object> stats = userService.getUserActivityStats(userId);
            return ApiResponse.success(stats);
        } catch (Exception e) {
            log.error("사용자 활동 통계 조회 중 오류 발생. userId: {}", userId, e);
            return ApiResponse.error("사용자 활동 통계 조회에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 주문 이력 조회
     */
    @GetMapping("/{userId}/order-history")
    public ApiResponse<List<Map<String, Object>>> getUserOrderHistory(
            @PathVariable Long userId,
            @RequestParam(defaultValue = "10") Integer limit) {
        try {
            List<Map<String, Object>> orderHistory = userService.getUserOrderHistory(userId, limit);
            return ApiResponse.success(orderHistory);
        } catch (Exception e) {
            log.error("사용자 주문 이력 조회 중 오류 발생. userId: {}", userId, e);
            return ApiResponse.error("사용자 주문 이력 조회에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 등급별 통계
     */
    @GetMapping("/grade-statistics")
    public ApiResponse<List<Map<String, Object>>> getUserGradeStatistics() {
        try {
            List<Map<String, Object>> stats = userService.getUserGradeStatistics();
            return ApiResponse.success(stats);
        } catch (Exception e) {
            log.error("사용자 등급별 통계 조회 중 오류 발생", e);
            return ApiResponse.error("사용자 등급별 통계 조회에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 가입 추이 분석
     */
    @GetMapping("/registration-trend")
    public ApiResponse<List<Map<String, Object>>> getUserRegistrationTrend(
            @RequestParam String startDate,
            @RequestParam String endDate,
            @RequestParam(defaultValue = "DAY") String groupBy) {
        try {
            List<Map<String, Object>> trend = userService.getUserRegistrationTrend(startDate, endDate, groupBy);
            return ApiResponse.success(trend);
        } catch (Exception e) {
            log.error("사용자 가입 추이 분석 중 오류 발생", e);
            return ApiResponse.error("사용자 가입 추이 분석에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 상태 업데이트
     */
    @PutMapping("/{userId}/status")
    public ApiResponse<Void> updateUserStatus(
            @PathVariable Long userId,
            @RequestParam String status) {
        try {
            userService.updateUserStatus(userId, status);
            return ApiResponse.success(null, "사용자 상태가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("사용자 상태 업데이트 중 오류 발생. userId: {}, status: {}", userId, status, e);
            return ApiResponse.error("사용자 상태 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 정보 업데이트
     */
    @PutMapping("/{userId}")
    public ApiResponse<Void> updateUserInfo(
            @PathVariable Long userId,
            @RequestBody UserDto userDto) {
        try {
            userDto.setUserId(userId);
            userService.updateUserInfo(userDto);
            return ApiResponse.success(null, "사용자 정보가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("사용자 정보 업데이트 중 오류 발생. userId: {}", userId, e);
            return ApiResponse.error("사용자 정보 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 사용자 삭제
     */
    @DeleteMapping("/{userId}")
    public ApiResponse<Void> deleteUser(@PathVariable Long userId) {
        try {
            userService.deleteUser(userId);
            return ApiResponse.success(null, "사용자가 성공적으로 삭제되었습니다.");
        } catch (Exception e) {
            log.error("사용자 삭제 중 오류 발생. userId: {}", userId, e);
            return ApiResponse.error("사용자 삭제에 실패했습니다.");
        }
    }
}
