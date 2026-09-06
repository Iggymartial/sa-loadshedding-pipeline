package com.loadshedding.api.controller;

import com.loadshedding.api.dto.SourceResponse;
import com.loadshedding.api.service.SourceService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/sources")
public class SourceController {

    private final SourceService sourceService;

    public SourceController(SourceService sourceService) {
        this.sourceService = sourceService;
    }

    // GET /api/sources - every known source (eskom, capetown, etc.)
    @GetMapping
    public List<SourceResponse> getAllSources() {
        return sourceService.getAllSources();
    }
}
