export type Source = {
  id: string;
  label: string;
  defaultChecked: boolean;
  storeKey: string | null;
  comingSoon: boolean;
};

export const SOURCES: readonly Source[] = [
  {
    id: "foreign-academic",
    label: "foreign academic",
    defaultChecked: true,
    storeKey: "foreign_academic",
    comingSoon: false,
  },
  {
    id: "local-academic",
    label: "local academic",
    defaultChecked: true,
    storeKey: "local_academic",
    comingSoon: false,
  },
  {
    id: "stray-dog-regional-advisory-panel",
    label: "Stray Dog Regional Advisory Panel",
    defaultChecked: true,
    storeKey: "onground_advocate",
    comingSoon: false,
  },
  {
    id: "ministry-of-fisheries-press-releases",
    label: "Ministry of Fisheries, Animal Husbandry & Dairying Press Releases",
    defaultChecked: true,
    storeKey: "goi_pib",
    comingSoon: false,
  },
  { id: "news", label: "news", defaultChecked: false, storeKey: null, comingSoon: true },
  { id: "reddit", label: "Reddit", defaultChecked: false, storeKey: null, comingSoon: true },
  { id: "linkedin", label: "LinkedIn", defaultChecked: false, storeKey: null, comingSoon: true },
  {
    id: "political-party-manifestos",
    label: "Political Party Manifestos",
    defaultChecked: false,
    storeKey: null,
    comingSoon: true,
  },
  { id: "parliament", label: "Parliament", defaultChecked: false, storeKey: null, comingSoon: true },
  {
    id: "government-data",
    label: "Government Data",
    defaultChecked: false,
    storeKey: null,
    comingSoon: true,
  },
  {
    id: "our-world-in-data",
    label: "Our World in Data",
    defaultChecked: false,
    storeKey: null,
    comingSoon: true,
  },
];

export function selectedStoreKeys(checked: Record<string, boolean>): string[] {
  return SOURCES.filter((s) => !s.comingSoon && s.storeKey && checked[s.id])
    .map((s) => s.storeKey as string);
}
