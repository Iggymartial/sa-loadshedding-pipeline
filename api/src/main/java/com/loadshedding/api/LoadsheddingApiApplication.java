package com.loadshedding.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the load shedding data API.
 *
 * This application is deliberately READ-ONLY: it never writes to
 * sources, stage_readings, or ingestion_runs. Those tables are owned
 * and populated exclusively by the Python data engineering pipeline
 * (extractor -> transform -> loader). This API's only job is to serve
 * that data out over HTTP.
 */
@SpringBootApplication
public class LoadsheddingApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoadsheddingApiApplication.class, args);
    }
}
