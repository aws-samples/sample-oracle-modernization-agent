package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

@Data
public class ProductRecommendationDto {
    private Long productId;
    private String productName;
    private String categoryName;
    private String brandName;
    private BigDecimal price;
    private BigDecimal avgRating;
    private Long totalSold;
    private BigDecimal revenue;
    private Long salesRank;
    private String performanceCategory;
    private BigDecimal recommendationScore;
    private Long recommendationRank;
    private String recommendationReason;
}
