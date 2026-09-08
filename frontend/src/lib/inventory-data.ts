export type AssetRow = {
  id: string;
  tag: string;
  name: string;
  status: "Assigned" | "New" | "Maintenance";
  owner: string;
  location: string;
  manufacturer: string;
  source: string;
  model: string;
  osName: string;
};

export const assets: AssetRow[] = [
  {
    id: "1",
    tag: "COM-0075",
    name: "Notebook corporativo",
    status: "Assigned",
    owner: "Aaron Costantino",
    location: "Buenos Aires",
    manufacturer: "Dell",
    source: "Agent",
    model: "XPS 15 7590",
    osName: "Ubuntu",
  },
  {
    id: "2",
    tag: "MON-0027",
    name: "Monitor 24 pol",
    status: "Assigned",
    owner: "Aaron Costantino",
    location: "Buenos Aires",
    manufacturer: "LG Electronics",
    source: "Manual",
    model: "24MP60VQ-P",
    osName: "-",
  },
  {
    id: "3",
    tag: "PHN-0009",
    name: "Celular corporativo",
    status: "New",
    owner: "",
    location: "Buenos Aires",
    manufacturer: "Motorola",
    source: "Agent",
    model: "Edge",
    osName: "Android",
  },
];

