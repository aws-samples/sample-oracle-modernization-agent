package amzn.bo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/**
 * AMZN 백오피스 애플리케이션 메인 클래스
 */
@SpringBootApplication
@EnableTransactionManagement
public class AmznBackOfficeApplication {

    public static void main(String[] args) {
        SpringApplication.run(AmznBackOfficeApplication.class, args);
    }
}
