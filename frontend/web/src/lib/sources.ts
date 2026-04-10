export type Source = {
  id: string;
  label: string;
  defaultChecked: boolean;
};

export const SOURCES: readonly Source[] = [
  { id: "foreign-academic", label: "foreign academic", defaultChecked: true },
  { id: "local-academic", label: "local academic", defaultChecked: false },
  { id: "news", label: "news", defaultChecked: true },
  { id: "reddit", label: "Reddit", defaultChecked: false },
  { id: "linkedin", label: "LinkedIn", defaultChecked: false },
  {
    id: "stray-dog-regional-advisory-panel",
    label: "Stray Dog Regional Advisory Panel",
    defaultChecked: false,
  },
  {
    id: "political-party-manifestos",
    label: "Political Party Manifestos",
    defaultChecked: true,
  },
  { id: "parliament", label: "Parliament", defaultChecked: false },
  { id: "government-data", label: "Government Data", defaultChecked: false },
  { id: "our-world-in-data", label: "Our World in Data", defaultChecked: false },
];
