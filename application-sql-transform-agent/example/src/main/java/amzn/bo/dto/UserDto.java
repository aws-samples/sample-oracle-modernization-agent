package amzn.bo.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * AMZN 백오피스 사용자 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserDto {
    
    private Long userId;
    private String email;
    private String firstName;
    private String lastName;
    private String phone;
    private String status;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime updatedAt;
    
    // 주문 통계 정보
    private Long orderCount;
    private BigDecimal totalSpent;
    private BigDecimal avgOrderValue;
    private Integer statusPriority;
    private Integer spendingRank;
    private String userGrade;
    private Integer daysSinceRegistration;
    private Long rn;
    
    // 검색 조건용 필드들
    private String searchKeyword;
    private String userGradeFilter;
    private Integer minOrderCount;
    private BigDecimal minTotalSpent;
    private String sortBy;
    private String sortDirection;
    private Integer page;
    private Integer size;
}
