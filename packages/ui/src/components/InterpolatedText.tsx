import type { ReactNode } from 'react';

/**
 * Stands in for the styled value while the catalog string is interpolated.
 *
 * It never reaches a catalog: it is passed as the *value* of an ordinary
 * `{name}` placeholder and split back out here, so the only thing a translator
 * ever sees — or has to move — is `{name}`. NUL is the sentinel because no
 * sentence in any language contains one, where a zero-width joiner or a
 * private-use character can legitimately appear in CJK and Indic copy.
 */
const SLOT = '\u0000';

interface Props {
  /**
   * Produce the finished sentence, passing `slot` as the value of the
   * placeholder the markup belongs at:
   * `(slot) => t(keys.x.y, { permission: slot })`.
   */
  render: (slot: string) => string;
  /** The value itself, free to carry its own markup. */
  children: ReactNode;
}

/**
 * One translated sentence with one value rendered as markup inside it.
 *
 * The alternative — a `prefix` key and a `suffix` key spliced around the value
 * — hands a translator two sentence fragments and no way to move the value,
 * which is the first thing a language with a different word order needs to do.
 * Here the whole sentence stays one key with one ordinary placeholder, and the
 * value keeps its own `<code>`/`<b>` styling.
 */
export function InterpolatedText({ render, children }: Props) {
  const [before, ...rest] = render(SLOT).split(SLOT);

  // A translation that dropped the placeholder still has to show the value.
  // Appending it reads awkwardly, but rendering `before` alone would silently
  // delete the one word the sentence exists to name.
  if (rest.length === 0) {
    return (
      <>
        {before} {children}
      </>
    );
  }

  // Repeating the placeholder is a mistake too, but the text around each copy
  // is real translated copy — keep all of it, and render the value once.
  return (
    <>
      {before}
      {children}
      {rest.join('')}
    </>
  );
}
