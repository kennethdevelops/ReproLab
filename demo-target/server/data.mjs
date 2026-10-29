// Synthetic seed data. No real products, people or payment details.

const CATEGORIES = ['Kitchen', 'Outdoor', 'Office', 'Home']

const NAMES = {
  Kitchen: [
    'Cast Iron Skillet', 'Bamboo Cutting Board', 'Pour-Over Kettle', 'Ceramic Mixing Bowls',
    'Chef Knife 8in', 'Spice Rack Set', 'Glass Storage Jars', 'Silicone Spatula Trio',
  ],
  Outdoor: [
    'Trail Water Bottle', 'Folding Camp Chair', 'Packable Rain Shell', 'Headlamp 300lm',
    'Insulated Picnic Tote', 'Compact Hammock', 'Stainless Camp Mug', 'Hiking Socks 2-Pack',
  ],
  Office: [
    'Walnut Desk Organizer', 'Dot Grid Notebook', 'Monitor Riser', 'Gel Pen Set',
    'Cable Management Kit', 'Laptop Sleeve 14in', 'Desk Lamp LED', 'Felt Desk Mat',
  ],
  Home: [
    'Linen Throw Pillow', 'Soy Candle Cedar', 'Woven Storage Basket', 'Wool Blanket',
    'Stoneware Vase', 'Cotton Bath Towels', 'Wall Clock Minimal', 'Ceramic Planter',
  ],
}

// Deterministic prices: no randomness, so every reset yields identical data.
export const PRODUCTS = CATEGORIES.flatMap((category, c) =>
  NAMES[category].map((name, i) => ({
    id: `p${String(c * 8 + i + 1).padStart(3, '0')}`,
    name,
    category,
    priceCents: 900 + ((c * 8 + i) * 1373) % 7100,
    rating: Number((3.5 + ((c * 8 + i) * 7) % 15 / 10).toFixed(1)),
  })),
)

export const COUPONS = [
  { code: 'SAVE10', percentOff: 10, expiresOn: '2099-12-31' },
  { code: 'WELCOME5', percentOff: 5, expiresOn: '2099-12-31' },
  { code: 'SUMMER23', percentOff: 20, expiresOn: '2023-08-31' },
]

export const SHIPPING_OPTIONS = [
  { id: 'standard', label: 'Standard (5–7 days)', priceCents: 499 },
  { id: 'express', label: 'Express (2 days)', priceCents: 1299 },
  { id: 'pickup', label: 'Store pickup', priceCents: 0 },
]

export function initialProfile() {
  return {
    displayName: 'Alex Rivera',
    email: 'alex.rivera@example.test',
    newsletter: false,
  }
}
