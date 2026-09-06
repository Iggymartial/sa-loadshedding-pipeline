package com.loadshedding.api.service;

import com.loadshedding.api.dto.IngestionRunResponse;
import com.loadshedding.api.repository.IngestionRunRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class IngestionRunService {

    private final IngestionRunRepository ingestionRunRepository;

    public IngestionRunService(IngestionRunRepository ingestionRunRepository) {
        this.ingestionRunRepository = ingestionRunRepository;
    }

    public List<IngestionRunResponse> getRecentRuns() {
        return ingestionRunRepository.findTop50ByOrderByRunAtDesc().stream()
                .map(r -> new IngestionRunResponse(
                        r.getId(),
                        r.getRunAt(),
                        r.getStatus().name(),
                        r.getRecordsFetched(),
                        r.getRawFile(),
                        r.getErrorMessage(),
                        r.getNotes()
                ))
                .toList();
    }
}
