package com.loadshedding.api.controller;

import com.loadshedding.api.dto.IngestionRunResponse;
import com.loadshedding.api.service.IngestionRunService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/ingestion-runs")
public class IngestionRunController {

    private final IngestionRunService ingestionRunService;

    public IngestionRunController(IngestionRunService ingestionRunService) {
        this.ingestionRunService = ingestionRunService;
    }

    // GET /api/ingestion-runs - the pipeline's own audit log: did recent
    // runs succeed, how many records did they load, what failed and why
    @GetMapping
    public List<IngestionRunResponse> getRecentRuns() {
        return ingestionRunService.getRecentRuns();
    }
}
