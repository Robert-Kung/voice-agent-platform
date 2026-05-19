import { redirect } from 'next/navigation';

export default async function ProfileEditorV2Redirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/admin/profiles/${id}`);
}
