-- Apply after `python manage.py migrate` in the dedicated rental Supabase project.
-- Public clients can read only published listings and their associated photos.
ALTER TABLE public.rental_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rental_listing_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rental_inspection_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rental_admin_profiles ENABLE ROW LEVEL SECURITY;

GRANT SELECT ON public.rental_listings TO anon, authenticated;
GRANT SELECT ON public.rental_listing_photos TO anon, authenticated;

CREATE POLICY "Public can read published rental listings"
    ON public.rental_listings
    FOR SELECT
    TO anon, authenticated
    USING (status = 'published');

CREATE POLICY "Public can read photos for published rental listings"
    ON public.rental_listing_photos
    FOR SELECT
    TO anon, authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM public.rental_listings
            WHERE rental_listings.id = rental_listing_photos.listing_id
              AND rental_listings.status = 'published'
        )
    );
