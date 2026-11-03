ALTER TABLE public.rental_listings
    ADD COLUMN IF NOT EXISTS landlord_whatsapp varchar(40) NOT NULL DEFAULT '';

REVOKE SELECT ON public.rental_listings FROM anon, authenticated;
GRANT SELECT (
    id,
    category,
    transaction_type,
    title,
    slug,
    description,
    address,
    city,
    state,
    property_type,
    bedrooms,
    bathrooms,
    annual_rent,
    sale_price,
    video_url,
    status,
    created_at,
    updated_at
) ON public.rental_listings TO anon, authenticated;
