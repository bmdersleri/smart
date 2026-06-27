// A lab dashboard can be generated once a sample point and >=1 parameter are chosen.
export function canGenerateLab(pointId: number | '' | string, paramIds: number[]): boolean {
  return pointId !== '' && pointId !== undefined && paramIds.length > 0
}
