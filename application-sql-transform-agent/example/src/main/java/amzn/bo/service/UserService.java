package amzn.bo.service;

import amzn.bo.dto.PageResponse;
import amzn.bo.dto.UserDto;
import amzn.bo.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 사용자 서비스
 */
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserService {
    
    private final UserMapper userMapper;
    
    /**
     * 사용자 목록 조회 (페이징)
     */
    public PageResponse<UserDto> getUserList(UserDto searchCondition) {
        Map<String, Object> params = buildSearchParams(searchCondition);
        
        // 페이징 처리
        int page = searchCondition.getPage() != null ? searchCondition.getPage() : 0;
        int size = searchCondition.getSize() != null ? searchCondition.getSize() : 20;
        int offset = page * size;
        
        params.put("offset", offset);
        params.put("limit", size);
        
        List<UserDto> users = userMapper.selectUserList(params);
        long totalCount = userMapper.selectUserCount(params);
        
        return PageResponse.of(users, page, size, totalCount);
    }
    
    /**
     * 사용자 상세 정보 조회
     */
    public UserDto getUserDetail(Long userId) {
        UserDto user = userMapper.selectUserDetail(userId);
        if (user == null) {
            throw new RuntimeException("사용자를 찾을 수 없습니다. ID: " + userId);
        }
        return user;
    }
    
    /**
     * 사용자 활동 통계 조회
     */
    public Map<String, Object> getUserActivityStats(Long userId) {
        return userMapper.selectUserActivityStats(userId);
    }
    
    /**
     * 사용자 주문 이력 조회
     */
    public List<Map<String, Object>> getUserOrderHistory(Long userId, Integer limit) {
        return userMapper.selectUserOrderHistory(userId, limit != null ? limit : 10);
    }
    
    /**
     * 사용자 등급별 통계
     */
    public List<Map<String, Object>> getUserGradeStatistics() {
        return userMapper.selectUserGradeStatistics();
    }
    
    /**
     * 사용자 가입 추이 분석
     */
    public List<Map<String, Object>> getUserRegistrationTrend(String startDate, String endDate, String groupBy) {
        return userMapper.selectUserRegistrationTrend(startDate, endDate, groupBy);
    }
    
    /**
     * 사용자 상태 업데이트
     */
    @Transactional
    public void updateUserStatus(Long userId, String status) {
        int result = userMapper.updateUserStatus(userId, status);
        if (result == 0) {
            throw new RuntimeException("사용자 상태 업데이트에 실패했습니다. ID: " + userId);
        }
        log.info("사용자 상태 업데이트 완료. ID: {}, Status: {}", userId, status);
    }
    
    /**
     * 사용자 정보 업데이트
     */
    @Transactional
    public void updateUserInfo(UserDto userDto) {
        int result = userMapper.updateUserInfo(userDto);
        if (result == 0) {
            throw new RuntimeException("사용자 정보 업데이트에 실패했습니다. ID: " + userDto.getUserId());
        }
        log.info("사용자 정보 업데이트 완료. ID: {}", userDto.getUserId());
    }
    
    /**
     * 사용자 삭제
     */
    @Transactional
    public void deleteUser(Long userId) {
        int result = userMapper.deleteUser(userId);
        if (result == 0) {
            throw new RuntimeException("사용자 삭제에 실패했습니다. ID: " + userId);
        }
        log.info("사용자 삭제 완료. ID: {}", userId);
    }
    
    /**
     * 검색 조건 파라미터 빌드
     */
    private Map<String, Object> buildSearchParams(UserDto searchCondition) {
        Map<String, Object> params = new HashMap<>();
        
        if (searchCondition.getEmail() != null && !searchCondition.getEmail().trim().isEmpty()) {
            params.put("email", searchCondition.getEmail().trim());
        }
        
        if (searchCondition.getStatus() != null && !searchCondition.getStatus().trim().isEmpty()) {
            params.put("status", searchCondition.getStatus().trim());
        }
        
        if (searchCondition.getUserGradeFilter() != null && !searchCondition.getUserGradeFilter().trim().isEmpty()) {
            params.put("userGrade", searchCondition.getUserGradeFilter().trim());
        }
        
        if (searchCondition.getMinOrderCount() != null) {
            params.put("minOrderCount", searchCondition.getMinOrderCount());
        }
        
        if (searchCondition.getMinTotalSpent() != null) {
            params.put("minTotalSpent", searchCondition.getMinTotalSpent());
        }
        
        if (searchCondition.getSearchKeyword() != null && !searchCondition.getSearchKeyword().trim().isEmpty()) {
            params.put("searchKeyword", searchCondition.getSearchKeyword().trim());
        }
        
        // 정렬 조건
        String sortBy = searchCondition.getSortBy() != null ? searchCondition.getSortBy() : "CREATED_AT";
        String sortDirection = searchCondition.getSortDirection() != null ? searchCondition.getSortDirection() : "DESC";
        params.put("sortBy", sortBy);
        params.put("sortDirection", sortDirection);
        
        return params;
    }
}
