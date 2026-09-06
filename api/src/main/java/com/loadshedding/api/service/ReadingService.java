package com.loadshedding.api.service;

import com.loadshedding.api.dto.ReadingResponse;
import com.loadshedding.api.entity.StageReading;
import com.loadshedding.api.repository.StageReadingRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ReadingService {

    private final StageReadingRepository stageReadingRepository;

    public ReadingService(StageReadingRepository stageReadingRepository) {
        this.stageReadingRepository = stageReadingRepository;
    }

    public List<ReadingResponse> getLatestPerSource() {
        return stageReadingRepository.findLatestPerSource().stream()
                .map(this::toResponse)
                .toList();
    }

    public List<ReadingResponse> getRecentReadings() {
        return stageReadingRepository.findTop100ByOrderByRecordedAtDesc().stream()
                .map(this::toResponse)
                .toList();
    }

    public List<ReadingResponse> getReadingsForSource(String code) {
        return stageReadingRepository.findBySource_CodeOrderByRecordedAtDesc(code).stream()
                .map(this::toResponse)
                .toList();
    }

    private ReadingResponse toResponse(StageReading reading) {
        return new ReadingResponse(
                reading.getId(),
                reading.getSource().getCode(),
                reading.getSource().getDisplayName(),
                reading.getStage(),
                reading.getStageUpdated(),
                reading.getRecordedAt()
        );
    }
}
