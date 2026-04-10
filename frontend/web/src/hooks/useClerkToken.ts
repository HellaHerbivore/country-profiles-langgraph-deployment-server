import { useEffect } from "react";
import { useAuth } from "@clerk/clerk-react";

import { setTokenGetter } from "@/lib/api";

/**
 * Registers Clerk's getToken function with the api module so all authenticated
 * fetch calls use a fresh JWT without any manual polling. clerk-react
 * automatically refreshes sessions internally.
 */
export function useClerkToken() {
  const { getToken, isSignedIn } = useAuth();

  useEffect(() => {
    if (!isSignedIn) {
      setTokenGetter(null);
      return;
    }
    setTokenGetter(async (opts) => {
      try {
        return await getToken(opts);
      } catch {
        return null;
      }
    });
    return () => {
      setTokenGetter(null);
    };
  }, [getToken, isSignedIn]);
}
