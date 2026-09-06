package com.loadshedding.api.repository;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * @DataJpaTest spins up an in-memory H2 database (see
 * src/test/resources/application.properties) and only loads JPA-related
 * beans, not the whole Spring context - fast, and needs no MySQL/Docker
 * running.
 */
@DataJpaTest
class SourceRepositoryTest {

    @Autowired
    private SourceRepository sourceRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findByCode_returnsSourceWhenItExists() {
        // Source has no public constructor/setters by design (see the
        // entity) - inserted via native SQL here instead of building an
        // entity directly, keeping entities read-only even inside tests.
        entityManager.getEntityManager()
                .createNativeQuery("INSERT INTO sources (code, display_name) VALUES ('eskom', 'Eskom')")
                .executeUpdate();
        entityManager.flush();
        entityManager.clear();

        var result = sourceRepository.findByCode("eskom");

        assertThat(result).isPresent();
        assertThat(result.get().getDisplayName()).isEqualTo("Eskom");
    }

    @Test
    void findByCode_returnsEmptyWhenSourceDoesNotExist() {
        var result = sourceRepository.findByCode("doesnotexist");
        assertThat(result).isEmpty();
    }
}
