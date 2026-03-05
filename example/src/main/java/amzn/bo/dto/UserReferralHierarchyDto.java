package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class UserReferralHierarchyDto {
    private Long userId;
    private String email;
    private String status;
    private LocalDateTime createdAt;
    private Long referredByUserId;
    private String referrerEmail;
    private Long referralLevel;
    private Long directReferrals;
    private Long totalReferrals;
    private BigDecimal totalSpent;
    private BigDecimal referralValue;
    private String referralPath;
}
