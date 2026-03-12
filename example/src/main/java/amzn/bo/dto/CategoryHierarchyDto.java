package amzn.bo.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * AMZN 백오피스 카테고리 계층 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CategoryHierarchyDto {
    
    private Long categoryId;
    private Long parentCategoryId;
    private String categoryName;
    private String description;
    private Integer categoryLevel;
    private String categoryPath;
    private String rootCategory;
    private Integer isLeaf;
    private Long productCount;
    private Long totalProductCountIncludingSubcategories;
    private Integer sortOrder;
    private String isActive;
}
