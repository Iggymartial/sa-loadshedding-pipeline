package com.loadshedding.api.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Maps to the `stage_readings` table (see db/schema.sql). This is the
 * time-series data written by the Python loader after validation.
 */
@Entity
@Table(name = "stage_readings")
public class StageReading {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "source_id", nullable = false)
    private Source source;

    @Column(nullable = false)
    private Integer stage;

    @Column(name = "stage_updated", nullable = false)
    private LocalDateTime stageUpdated;

    @Column(name = "recorded_at", nullable = false)
    private LocalDateTime recordedAt;

    @Column(name = "raw_file", nullable = false)
    private String rawFile;

    protected StageReading() {
        // required by JPA/Hibernate
    }

    public Integer getId() {
        return id;
    }

    public Source getSource() {
        return source;
    }

    public Integer getStage() {
        return stage;
    }

    public LocalDateTime getStageUpdated() {
        return stageUpdated;
    }

    public LocalDateTime getRecordedAt() {
        return recordedAt;
    }

    public String getRawFile() {
        return rawFile;
    }
}
