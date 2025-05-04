

CREATE TABLE test_stored.internal_songs (
	id serial4 NOT NULL,
	code varchar(255) NOT NULL,
	original_artist varchar(255) NULL,
	song_title varchar(255) NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT internal_songs_code_key UNIQUE (code),
	CONSTRAINT internal_songs_pkey PRIMARY KEY (id)
);


CREATE TABLE test_stored.spotify_metadata (
	id serial4 NOT NULL,
	code varchar(255) NOT NULL,
	isrc varchar(15) NOT NULL,
	original_artist varchar(255) NULL,
	song_title varchar(255) NULL,
	spotify_title varchar(255) NULL,
	spotify_artist varchar(255) NULL,
	album varchar(255) NULL,
	release_date date NULL,
	spotify_url varchar(255) NULL,
	duration_seconds int4 NULL,
	monthly_listeners int4 NULL,
	popularity int4 NULL,
	artist_genres varchar(255) NULL,
	ingest_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT spotify_metadata_code_key UNIQUE (code),
	CONSTRAINT spotify_metadata_isrc_key UNIQUE (isrc),
	CONSTRAINT spotify_metadata_pkey PRIMARY KEY (id)
);



CREATE TABLE test_stored.youtube_metadata (
	id serial4 NOT NULL,
	code varchar(255) NOT NULL,
	channel_id varchar(255) NULL,
	original_artist varchar(255) NULL,
	song_title varchar(255) NULL,
	video_id varchar(255) NULL,
	video_title varchar(255) NULL,
	channel_name varchar(255) NULL,
	"views" varchar(255) NULL,
	artist_found varchar(255) NULL,
	song_title_found varchar(255) NULL,
	video_url text NULL,
	upload_date date NULL,
	ingest_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT youtube_metadata_code_key UNIQUE (code),
	CONSTRAINT youtube_metadata_pkey PRIMARY KEY (id)
);



CREATE TABLE test_stored.youtube_cleaned_data (
	id serial4 NOT NULL,
	code varchar(255) NOT NULL,
	channel_id varchar(255) NULL,
	original_artist varchar(255) NULL,
	song_title varchar(255) NULL,
	video_id varchar(255) NULL,
	video_title varchar(255) NULL,
	channel_name varchar(255) NULL,
	"views" varchar(255) NULL,
	artist_found varchar(255) NULL,
	song_title_found varchar(255) NULL,
	video_url text NULL,
	upload_date date NULL,
	ingest_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	"valid" bool NULL,
	CONSTRAINT youtube_cleaned_data_code_key UNIQUE (code),
	CONSTRAINT youtube_cleaned_data_pkey PRIMARY KEY (id)
);


CREATE TABLE test_stored.clean_songs_data (
	song_id serial4 NOT NULL,
	code varchar(255) NOT NULL,
	original_artist varchar(255) NULL,
	song_title varchar(255) NULL,
	standardized_title varchar(255) NULL,
	standardized_artist varchar(255) NULL,
	isrc varchar(15) NULL,
	spotify_title varchar(255) NULL,
	spotify_artist varchar(255) NULL,
	album varchar(255) NULL,
	release_date date NULL,
	spotify_url text NULL,
	duration_seconds int4 NULL,
	monthly_listeners int4 NULL,
	popularity int4 NULL,
	youtube_video_id varchar(255) NULL,
	youtube_title text NULL,
	channel_name varchar(255) NULL,
	"views" int8 NULL,
	video_url text NULL,
	upload_date date NULL,
	best_source varchar(10) NULL,
	data_quality_score int4 NULL,
	last_verified_at timestamp NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT clean_songs_code_unique UNIQUE (code),
	CONSTRAINT clean_songs_data_pkey PRIMARY KEY (song_id)
);