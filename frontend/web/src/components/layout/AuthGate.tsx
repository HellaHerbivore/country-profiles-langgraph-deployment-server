import type { PropsWithChildren } from "react";
import { SignedIn, SignedOut, SignIn, useAuth } from "@clerk/clerk-react";

import { Loader2 } from "lucide-react";

export function AuthGate({ children }: PropsWithChildren) {
  const { isLoaded } = useAuth();

  if (!isLoaded) {
    return (
      <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <>
      <SignedOut>
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-background p-4">
          <SignIn routing="hash" />
        </div>
      </SignedOut>
      <SignedIn>{children}</SignedIn>
    </>
  );
}
