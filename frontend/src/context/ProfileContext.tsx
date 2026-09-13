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
  setProfile: (profile: CustomerProfile) => void;
  refreshProfile: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined);

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const refreshProfile = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setProfile(null);
      return;
    }
    try {
      setIsLoading(true);
      setProfile(await getCustomerProfile(token));
    } catch {
      setProfile(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      refreshProfile();
    } else {
      setProfile(null);
    }
  }, [isAuthenticated, refreshProfile]);

  return (
    <ProfileContext.Provider
      value={{ profile, isLoading, setProfile, refreshProfile }}
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
