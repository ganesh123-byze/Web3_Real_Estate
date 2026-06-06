export const INVESTOR_MARKETPLACE_CATALOG_HEADING =
  "Here are the properties open for investment";

export type MarketplaceCatalogProperty = {
  id: number | null;
  name: string;
  location: string;
  saleProgress: string;
  tokensAvailable: string;
  pricePerToken: string;
  monthlyRent: string;
  grossAnnualYield: string;
  netProjectedYield: string;
};

export type MarketplaceCatalog = {
  heading: string;
  properties: MarketplaceCatalogProperty[];
  footer: string;
};

function parsePropertyBlock(block: string): MarketplaceCatalogProperty | null {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return null;

  const propertyMatch = lines[0]?.match(/^Property:\s*(.+?)\s*\(#(\d+)\)\s*$/i);
  if (!propertyMatch) return null;

  const row = (label: string) => {
    const line = lines.find((entry) => entry.toLowerCase().startsWith(`${label.toLowerCase()}:`));
    if (!line) return "—";
    return line.slice(label.length + 1).trim() || "—";
  };

  return {
    id: Number(propertyMatch[2]),
    name: propertyMatch[1].trim(),
    location: row("Location"),
    saleProgress: row("Sale progress"),
    tokensAvailable: row("Tokens available"),
    pricePerToken: row("Price per token"),
    monthlyRent: row("Monthly rent"),
    grossAnnualYield: row("Gross annual yield"),
    netProjectedYield: row("Net projected yield"),
  };
}

export function isMarketplaceCatalogContent(content: string): boolean {
  return content.trim().toLowerCase().includes(INVESTOR_MARKETPLACE_CATALOG_HEADING.toLowerCase());
}

export function parseMarketplaceCatalogContent(content: string): MarketplaceCatalog | null {
  const trimmed = content.trim();
  if (!isMarketplaceCatalogContent(trimmed)) return null;

  const footerMarker = "\nI've opened the marketplace";
  const footerIndex = trimmed.indexOf(footerMarker);
  const body = footerIndex >= 0 ? trimmed.slice(0, footerIndex).trim() : trimmed;
  const footer =
    footerIndex >= 0 ? trimmed.slice(footerIndex).trim() : "I've opened the marketplace.";

  const withoutHeading = body
    .replace(new RegExp(`^${INVESTOR_MARKETPLACE_CATALOG_HEADING}\\s*`, "i"), "")
    .trim();

  const propertyBlocks = withoutHeading
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);

  const properties = propertyBlocks
    .map((block) => parsePropertyBlock(block))
    .filter((property): property is MarketplaceCatalogProperty => property !== null);

  if (!properties.length) return null;

  return {
    heading: INVESTOR_MARKETPLACE_CATALOG_HEADING,
    properties,
    footer,
  };
}
