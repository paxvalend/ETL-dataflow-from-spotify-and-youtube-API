# ETL-dataflow-from-spotify-and-youtube-API

# Data Flow Diagram

```mermaid
flowchart TD
    A[Internal Songs] -.-> D[Extract Data]
    B[Spotify Metadata] -.-> D
    C[YouTube Metadata] -.-> D
    
    D -.-> E[Transform & Cleanse]
    
    subgraph E[Transform & Cleanse]
        E1[Standardisasi Data]
        E2[Deduplikasi]
        E3[Penanganan Nilai yang Hilang]
    end
    
    E -.-> F[Load Data]
    
    subgraph F[Load Data]
        F1[Artists] 
        F2[Albums]
        F3[Songs]
        F3 -.-> F4[Spotify Data]
        F3 -.-> F5[YouTube Data]
    end
    
    F -.-> G[Validasi & Monitoring]
```

## Description

This diagram illustrates the data processing pipeline for music metadata:

1. **Data Sources**:
   - Internal Songs database
   - Spotify Metadata
   - YouTube Metadata

2. **Extract Data**:
   - Collects data from all three sources

3. **Transform & Cleanse**:
   - Standardizes data formats
   - Removes duplicates
   - Handles missing values

4. **Load Data**:
   - Organizes into Artists, Albums, and Songs
   - Songs data further splits into Spotify and YouTube specific data

5. **Validation & Monitoring**:
   - Ensures data quality and system performance
