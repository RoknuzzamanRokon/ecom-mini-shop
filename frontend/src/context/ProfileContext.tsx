"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { CustomerProfile } from "@/lib/types";
import { getCustomerProfile } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { useAuth } from "./AuthContext";

interface ProfileContextType {
  profile: CustomerProfile | null;
  isLoading: boolean;
  /**
   * Why the profile could not be loaded, until a load succeeds. A failed
   * reload keeps the profile already loaded; a failed first load leaves it
   * null, which is "not loaded", never "empty" (BUG-086).
   */
  error: string | null;
  setProfile: (profile: CustomerProfile) => void;
  refreshProfile: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined);

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshProfile = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setProfile(null);
      setError(null);
      return;
    }
    try {
      setIsLoading(true);
      setProfile(await getCustomerProfile(token));
      setError(null);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Your profile could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      refreshProfile();
    } else {
      setProfile(null);
      setError(null);
    }
  }, [isAuthenticated, refreshProfile]);

  return (
    <ProfileContext.Provider
      value={{ profile, isLoading, error, setProfile, refreshProfile }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  const context = useContext(ProfileContext);
  if (!context) {
    throw new Error("useProfile must be used within a ProfileProvider");
  }
  return context;
}
