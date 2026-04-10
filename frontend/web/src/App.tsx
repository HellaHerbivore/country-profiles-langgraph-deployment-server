import { AuthGate } from "@/components/layout/AuthGate";
import { AppShell } from "@/components/layout/AppShell";
import { ResearchContext } from "@/hooks/ResearchContext";
import { useClerkToken } from "@/hooks/useClerkToken";
import { useResearch } from "@/hooks/useResearch";

function AuthedApp() {
  useClerkToken();
  const research = useResearch();

  return (
    <ResearchContext.Provider value={research}>
      <AppShell />
    </ResearchContext.Provider>
  );
}

export default function App() {
  return (
    <AuthGate>
      <AuthedApp />
    </AuthGate>
  );
}
