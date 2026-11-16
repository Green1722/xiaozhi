"""Shared BMI guidance for query and proactive announcement."""
from decimal import Decimal


def lifestyle_guidance(bmi: Decimal, confirmed_adult: bool) -> str:
    if not confirmed_adult:
        return "可以在相同条件下定期复测，观察变化。若想按成人 BMI 范围解读，请先确认是否已满 18 岁。"
    # 国家卫生健康委《体重管理指导原则（2024年版）》附表 1。
    if bmi < Decimal("18.5"):
        return "按成人参考范围，这次 BMI 偏低。可以先复测，并留意近期食欲和体重变化；如果体重持续下降，可向校医咨询。"
    if bmi < Decimal("24"):
        return "这次 BMI 在成人参考范围内。可以保持规律运动和均衡饮食，用同样的条件复测并观察趋势。"
    if bmi < Decimal("28"):
        return "这次 BMI 高于成人参考范围。可以从日常可坚持的一件事开始，比如用白水替代含糖饮料，或安排适合自己的步行。"
    return "这次 BMI 明显高于成人参考范围。可以先在相同条件下复测，并向校医或体重管理门诊咨询适合自己的生活方式调整。"
