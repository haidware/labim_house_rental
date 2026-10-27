ALTER TABLE public.rental_listings
    ADD COLUMN IF NOT EXISTS video_url varchar(1000) NOT NULL DEFAULT '';

INSERT INTO storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
VALUES (
    'rental-listing-videos',
    'rental-listing-videos',
    true,
    104857600,
    ARRAY['video/mp4', 'video/quicktime', 'video/x-m4v', 'video/webm']
)
ON CONFLICT (id) DO UPDATE
SET public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "Public can view rental listing videos"
    ON storage.objects;
CREATE POLICY "Public can view rental listing videos"
    ON storage.objects
    FOR SELECT
    TO anon, authenticated
    USING (bucket_id = 'rental-listing-videos');
