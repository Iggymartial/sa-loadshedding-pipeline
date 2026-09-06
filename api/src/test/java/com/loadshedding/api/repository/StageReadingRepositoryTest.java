package com.loadshedding.api.repository;

import com.loadshedding.api.entity.StageReading;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class StageReadingRepositoryTest {

    @Autowired
    private StageReadingRepository stageReadingRepository;

    @Autowired
    private TestEntityManager entityManager;

    private void insertSource(String code, String name) {
        entityManager.getEntityManager()
                .createNativeQuery("INSERT INTO sources (code, display_name) VALUES (:code, :name)")
                .setParameter("code", code)
                .setParameter("name", name)
                .executeUpdate();
    }

    private void insertReading(String sourceCode, int stage, String stageUpdated, String recordedAt, String rawFile) {
        entityManager.getEntityManager()
                .createNativeQuery("""
                        INSERT INTO stage_readings (source_id, stage, stage_updated, recorded_at, raw_file)
                        VALUES ((SELECT id FROM sources WHERE code = :code), :stage, :stageUpdated, :recordedAt, :rawFile)
                        """)
                .setParameter("code", sourceCode)
                .setParameter("stage", stage)
                .setParameter("stageUpdated", stageUpdated)
                .setParameter("recordedAt", recordedAt)
                .setParameter("rawFile", rawFile)
                .executeUpdate();
    }

    @Test
    void findLatestPerSource_returnsOnlyTheMostRecentReadingForEachSource() {
        insertSource("eskom", "Eskom");
        insertSource("capetown", "Cape Town");

        // Eskom: two readings - the SECOND one is the more recent one
        insertReading("eskom", 0, "2026-01-01 10:00:00", "2026-01-01 10:05:00", "file1.json");
        insertReading("eskom", 2, "2026-01-02 10:00:00", "2026-01-02 10:05:00", "file2.json");

        // Cape Town: only one reading
        insertReading("capetown", 1, "2026-01-01 09:00:00", "2026-01-01 09:05:00", "file3.json");

        entityManager.flush();
        entityManager.clear();

        List<StageReading> latest = stageReadingRepository.findLatestPerSource();

        // Three readings went in, but only ONE per source should come back.
        assertThat(latest).hasSize(2);

        StageReading eskomLatest = latest.stream()
                .filter(r -> r.getSource().getCode().equals("eskom"))
                .findFirst()
                .orElseThrow();

        // Must be the LATER of Eskom's two readings, not just the first one inserted.
        assertThat(eskomLatest.getStage()).isEqualTo(2);
        assertThat(eskomLatest.getRawFile()).isEqualTo("file2.json");
    }

    @Test
    void findBySource_CodeOrderByRecordedAtDesc_returnsFullHistoryMostRecentFirst() {
        insertSource("eskom", "Eskom");
        insertReading("eskom", 0, "2026-01-01 10:00:00", "2026-01-01 10:05:00", "file1.json");
        insertReading("eskom", 2, "2026-01-02 10:00:00", "2026-01-02 10:05:00", "file2.json");
        entityManager.flush();
        entityManager.clear();

        List<StageReading> history = stageReadingRepository.findBySource_CodeOrderByRecordedAtDesc("eskom");

        assertThat(history).hasSize(2);
        assertThat(history.get(0).getRawFile()).isEqualTo("file2.json"); // most recent first
        assertThat(history.get(1).getRawFile()).isEqualTo("file1.json");
    }
}
