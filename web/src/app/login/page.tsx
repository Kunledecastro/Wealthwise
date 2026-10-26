"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { api, ApiError, type Me } from "@/lib/api";
import { loginSchema } from "@/lib/schemas";

type Values = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { me, loading, setMe } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(loginSchema) });

  useEffect(() => {
    if (!loading && me) router.replace("/");
  }, [loading, me, router]);

  async function onSubmit(values: Values) {
    setError(null);
    try {
      setMe(await api<Me>("/api/auth/login", { method: "POST", body: values }));
      router.replace("/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sign-in failed.");
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Welcome back."
      footer={<>New here? You need an invite link from your administrator.</>}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && <Alert>{error}</Alert>}
        <Field label="Email" type="email" autoComplete="email" inputMode="email" autoFocus error={formState.errors.email?.message} {...register("email")} />
        <Field label="Password" type="password" autoComplete="current-password" error={formState.errors.password?.message} {...register("password")} />
        <Button type="submit" size="full" loading={formState.isSubmitting}>Sign in</Button>
        <p className="text-center text-sm">
          <Link href="/forgot-password" className="text-[var(--accent)] underline-offset-4 hover:underline">Forgot your password?</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
