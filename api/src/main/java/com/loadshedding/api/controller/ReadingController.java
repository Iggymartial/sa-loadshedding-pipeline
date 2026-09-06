package com.loadshedding.api.controller;

import com.loadshedding.api.dto.ReadingResponse;
import com.loadshedding.api.service.ReadingService;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/readings")
public class ReadingController {

    private final ReadingService readingService;

    public ReadingController(ReadingService readingService) {
        this.readingService = readingService;
    }

    // GET /api/readings - most recent readings across all sources (up to 100)
    @GetMapping
    public List<ReadingResponse> getRecentReadings() {
        return readingService.getRecentReadings();
    }

    // GET /api/readings/latest - "what is the load shedding stage right now",
    // one row per source
    @GetMapping("/latest")
    public List<ReadingResponse> getLatestPerSource() {
        return readingService.getLatestPerSource();
    }

    // GET /api/readings/source/eskom - full history for one source
    @GetMapping("/source/{code}")
    public List<ReadingResponse> getReadingsForSource(@PathVariable String code) {
        return readingService.getReadingsForSource(code);
    }
}
