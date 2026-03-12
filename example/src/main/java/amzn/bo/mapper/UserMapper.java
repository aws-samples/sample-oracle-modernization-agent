package amzn.bo.mapper;

import amzn.bo.dto.UserDto;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 사용자 매퍼
 */
@Mapper
public interface UserMapper {
    
    /**
     * 사용자 목록 조회 (복합 검색, 고급 필터링)
     */
    List<UserDto> selectUserList(Map<String, Object> params);
    
    /**
     * 사용자 총 개수 조회
     */
    long selectUserCount(Map<String, Object> params);
    
    /**
     * 사용자 상세 정보 조회
     */
    UserDto selectUserDetail(@Param("userId") Long userId);
    
    /**
     * 사용자 활동 통계 조회
     */
    Map<String, Object> selectUserActivityStats(@Param("userId") Long userId);
    
    /**
     * 사용자 주문 이력 조회
     */
    List<Map<String, Object>> selectUserOrderHistory(@Param("userId") Long userId, 
                                                     @Param("limit") Integer limit);
    
    /**
     * 사용자 등급별 통계
     */
    List<Map<String, Object>> selectUserGradeStatistics();
    
    /**
     * 사용자 가입 추이 분석
     */
    List<Map<String, Object>> selectUserRegistrationTrend(@Param("startDate") String startDate,
                                                          @Param("endDate") String endDate,
                                                          @Param("groupBy") String groupBy);
    
    /**
     * 사용자 상태 업데이트
     */
    int updateUserStatus(@Param("userId") Long userId, @Param("status") String status);
    
    /**
     * 사용자 정보 업데이트
     */
    int updateUserInfo(UserDto userDto);
    
    /**
     * 사용자 삭제 (소프트 삭제)
     */
    int deleteUser(@Param("userId") Long userId);
}
