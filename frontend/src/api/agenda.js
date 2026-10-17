// STEP 1 (agenda maker) plugs in here.
//
// Right now this returns a hard-coded mock agenda. Later, replace the body of
// `fetchAgenda` with a call to your agenda generator, for example:
//
//   const res = await fetch("/agenda-maker/generate", { method: "POST", body: JSON.stringify({ source: "jira" }) });
//   return res.json();   // must return the same shape as MOCK_AGENDA below
//
// Shape of one item: { title: string, description?: string, minutes?: number }

export const MOCK_AGENDA = [
  {
    title: "Sprint review",
    description: "What shipped this sprint: features, bug fixes, demos of finished tickets",
    minutes: 10,
  },
  {
    title: "Blockers and risks",
    description: "Technical blockers, dependencies on other teams, deadline risks",
    minutes: 8,
  },
  {
    title: "Next sprint planning",
    description: "Priorities, ticket estimates, who takes what for the next sprint",
    minutes: 12,
  },
];

export async function fetchAgenda() {
  // Pretend to be a network call so the UI already handles a loading state.
  await new Promise((r) => setTimeout(r, 350));
  return MOCK_AGENDA.map((item) => ({ ...item }));
}
