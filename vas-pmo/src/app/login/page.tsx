import LoginForm from "./login-form";

/**
 * Server component: in Next 15 `searchParams` is a promise, so it is awaited here and the
 * plain value handed to the client form.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  return <LoginForm next={params?.next ?? "/portfolio"} />;
}
