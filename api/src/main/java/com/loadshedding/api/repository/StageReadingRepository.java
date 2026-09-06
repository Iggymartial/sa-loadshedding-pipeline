package com.loadshedding.api.repository;

import com.loadshedding.api.entity.StageReading;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface StageReadingRepository extends JpaRepository<StageReading, Integer> {

    /**
     * Full history for one source, most recent first. The underscore in
     * `Source_Code` tells Spring Data to traverse the `source` relationship
     * and filter on ITS `code` field, rather than looking for a (nonexistent)
     * flat property literally called `sourceCode` on StageReading.
     */
    List<StageReading> findBySource_CodeOrderByRecordedAtDesc(String code);

    /**
     * Most recent readings across all sources, capped at 100 - a general
     * "what's happened recently" view rather than the full table.
     */
    List<StageReading> findTop100ByOrderByRecordedAtDesc();

    /**
     * The single latest reading per source - answers "what is the load
     * shedding stage RIGHT NOW" for every source in one call.
     *
     * This can't be expressed as a simple derived query method (Spring
     * Data has no built-in "latest per group" pattern), so it's a
     * correlated subquery in JPQL: for each reading, only keep it if its
     * recorded_at equals the maximum recorded_at among all readings for
     * that same source.
     */
    @Query("""
            SELECT sr FROM StageReading sr
            WHERE sr.recordedAt = (
                SELECT MAX(sr2.recordedAt)
                FROM StageReading sr2
                WHERE sr2.source = sr.source
            )
            """)
    List<StageReading> findLatestPerSource();
}
